// Local Kultura OS plugin installer for Codex. Communicates with the official local Codex app-server over stdio.
package main

import (
	"archive/zip"
	"bufio"
	"bytes"
	"context"

	"encoding/json"
	"errors"
	"fmt"
	"io"

	"os"
	"os/exec"
	"path/filepath"

	"runtime"
	"strings"
	"time"
)

const serverName = "kultura_os"

var endpoint = "https://beerkultura.ru/mcp" // set from the published MCP manifest at build time

type client struct {
	cmd *exec.Cmd
	in  io.WriteCloser
	out *json.Decoder
	seq int
}

func (c *client) call(method string, params any, result any) error {
	c.seq++
	if err := json.NewEncoder(c.in).Encode(map[string]any{"id": c.seq, "method": method, "params": params}); err != nil {
		return err
	}
	for {
		var response struct {
			ID     int
			Result json.RawMessage
			Error  *struct{ Message string }
		}
		if err := c.out.Decode(&response); err != nil {
			return fmt.Errorf("%s: %w", method, err)
		}
		if response.ID != c.seq {
			continue
		}
		if response.Error != nil {
			return fmt.Errorf("%s: %s", method, response.Error.Message)
		}
		if result == nil {
			return nil
		}
		return json.Unmarshal(response.Result, result)
	}
}

func executable() (string, error) {
	if path, err := exec.LookPath("codex"); err == nil && (runtime.GOOS != "windows" || strings.EqualFold(filepath.Ext(path), ".exe")) {
		return path, nil
	}
	if runtime.GOOS == "windows" {
		// Microsoft Store desktop applications contain the CLI under resources.
		command := `Get-AppxPackage | Where-Object { $_.Name -match '^OpenAI\.(Codex|ChatGPT)(-|$)' -and $_.InstallLocation } | ForEach-Object { Get-ChildItem -LiteralPath $_.InstallLocation -Filter codex.exe -File -Recurse -ErrorAction SilentlyContinue } | Where-Object { $_.FullName -match '\\resources\\' } | Select-Object -First 1 -ExpandProperty FullName`
		out, err := exec.Command("powershell.exe", "-NoProfile", "-Command", command).Output()
		if err == nil {
			p := strings.TrimSpace(string(out))
			if filepath.IsAbs(p) {
				if _, err = os.Stat(p); err == nil {
					return p, nil
				}
			}
		}
	}
	return "", errors.New("Не найден Codex CLI в установленном приложении OpenAI")
}

func start(ctx context.Context, exe string) (*client, error) {
	cmd := exec.CommandContext(ctx, exe, "app-server")
	in, err := cmd.StdinPipe()
	if err != nil {
		return nil, err
	}
	out, err := cmd.StdoutPipe()
	if err != nil {
		return nil, err
	}
	if err = cmd.Start(); err != nil {
		return nil, err
	}
	c := &client{cmd: cmd, in: in, out: json.NewDecoder(out)}
	err = c.call("initialize", map[string]any{"clientInfo": map[string]string{"name": "kultura-local-connect", "version": "1"}, "capabilities": map[string]bool{"experimentalApi": true}}, nil)
	if err == nil {
		err = json.NewEncoder(in).Encode(map[string]string{"method": "initialized"})
	}
	if err != nil {
		c.close()
		return nil, err
	}
	return c, nil
}
func (c *client) close() { c.in.Close(); c.cmd.Process.Kill(); c.cmd.Wait() }

// Keep the marketplace available after installation. The directory is versioned so
// upgrading cannot change files used by an earlier plugin while it is running.
func unpack(bundle *zip.ReadCloser, parent string) (string, error) {
	if err := os.MkdirAll(parent, 0700); err != nil {
		return "", err
	}
	staging, err := os.MkdirTemp(parent, ".install-")
	if err != nil {
		return "", err
	}
	defer os.RemoveAll(staging)
	for _, f := range bundle.File {
		if !filepath.IsLocal(filepath.FromSlash(f.Name)) {
			return "", errors.New("Недопустимый путь в пакете")
		}
		path := filepath.Join(staging, filepath.FromSlash(f.Name))
		if err := os.MkdirAll(filepath.Dir(path), 0700); err != nil {
			return "", err
		}
		src, err := f.Open()
		if err != nil {
			return "", err
		}
		data, err := io.ReadAll(src)
		src.Close()
		if err != nil {
			return "", err
		}
		if err := os.WriteFile(path, data, 0600); err != nil {
			return "", err
		}
	}
	root := filepath.Join(parent, "kultura-os-1.1.2")
	if err := os.Rename(staging, root); err != nil {
		// A previous or concurrent install is usable only if it has identical files.
		for _, f := range bundle.File {
			path := filepath.FromSlash(f.Name)
			a, ea := os.ReadFile(filepath.Join(root, path))
			b, eb := os.ReadFile(filepath.Join(staging, path))
			if ea != nil || eb != nil || !bytes.Equal(a, b) {
				return "", err
			}
		}
	}
	return root, nil
}

type server struct {
	Name      string
	Enabled   bool
	Auth      string `json:"auth_status"`
	Transport struct{ Type, URL string }
}

func findServer(ctx context.Context, exe string) (*server, error) {
	out, err := exec.CommandContext(ctx, exe, "mcp", "list", "--json").Output()
	if err != nil {
		return nil, fmt.Errorf("Codex не прочитал список локальных серверов MCP: %w", err)
	}
	var servers []server
	if err := json.Unmarshal(out, &servers); err != nil {
		return nil, err
	}
	for _, s := range servers {
		if s.Name != serverName {
			continue
		}
		if s.Transport.Type != "streamable_http" || s.Transport.URL != endpoint || !s.Enabled {
			return nil, errors.New("В Codex уже есть другая или отключённая конфигурация с именем kultura_os. Установка остановлена, настройки сохранены")
		}
		return &s, nil
	}
	return nil, nil
}

func connect(ctx context.Context, exe string) error {
	s, err := findServer(ctx, exe)
	if err != nil {
		return err
	}
	args := []string{"mcp", "add", serverName, "--url", endpoint}
	if s != nil {
		if s.Auth != "not_logged_in" && s.Auth != "unsupported" && s.Auth != "unknown" {
			return nil
		}
		args = []string{"mcp", "login", serverName}
	}
	fmt.Println("Подключаю Культуру. При первом входе подтвердите доступ на сайте в браузере.")
	cmd := exec.CommandContext(ctx, exe, args...)
	cmd.Stdout, cmd.Stderr = os.Stdout, os.Stderr
	if err := cmd.Run(); err != nil {
		return fmt.Errorf("Подключение MCP или вход прерваны: %w", err)
	}
	return nil
}

// Preserve the global plugin ID when upgrading an existing Kultura marketplace.
// Codex installs from an explicit path without adding it to the discovery list.
func registerMarketplace(c *client, root string) error {
	const name = "kultura-plugins"
	var settings struct {
		Config struct {
			Marketplaces map[string]struct {
				Type   string `json:"source_type"`
				Source string
			}
		}
	}
	if err := c.call("config/read", map[string]bool{"includeLayers": false}, &settings); err != nil {
		return err
	}
	if old, ok := settings.Config.Marketplaces[name]; ok && filepath.Clean(old.Source) != filepath.Clean(root) {
		known := false
		if old.Type == "local" && filepath.IsAbs(old.Source) {
			b, err := os.ReadFile(filepath.Join(old.Source, ".agents", "plugins", "marketplace.json"))
			var m struct {
				Name    string
				Plugins []struct{ Name string }
			}
			known = err == nil && json.Unmarshal(b, &m) == nil && m.Name == name && len(m.Plugins) == 1 && m.Plugins[0].Name == "kultura-os"
		} else if old.Type == "git" {
			repo := strings.TrimSuffix(old.Source, ".git")
			known = repo == "https://github.com/wwworm666/beer-abc-analysis" || repo == "wwworm666/beer-abc-analysis"
		}
		if !known {
			return errors.New("Имя каталога kultura-plugins занято другим источником. Установка остановлена")
		}
		return c.call("config/value/write", map[string]any{"keyPath": "marketplaces." + name, "mergeStrategy": "replace", "value": map[string]string{"source_type": "local", "source": root}}, nil)
	}
	return c.call("marketplace/add", map[string]string{"source": root}, nil)
}

func install(c *client, root string) error {
	selection := map[string]string{"pluginName": "kultura-os", "marketplacePath": filepath.Join(root, ".agents", "plugins", "marketplace.json")}
	if err := c.call("plugin/install", selection, nil); err != nil {
		return err
	}
	var detail struct {
		Plugin struct {
			Summary    struct{ Installed, Enabled bool }
			McpServers []string
			Skills     []json.RawMessage
		}
	}
	if err := c.call("plugin/read", selection, &detail); err != nil {
		return err
	}
	p := detail.Plugin
	if !p.Summary.Installed || !p.Summary.Enabled || len(p.Skills) != 2 || len(p.McpServers) != 0 {
		return errors.New("Codex не подтвердил установку плагина с двумя навыками")
	}
	return nil
}

func checkThread(c *client, root string) error {
	var started struct{ Thread struct{ ID string } }
	if err := c.call("thread/start", map[string]any{"cwd": root, "ephemeral": true}, &started); err != nil {
		return err
	}
	var inventory struct {
		Data []struct {
			Name  string
			Tools map[string]json.RawMessage
		}
	}
	if err := c.call("mcpServerStatus/list", map[string]any{"threadId": started.Thread.ID, "serverName": serverName, "detail": "toolsAndAuthOnly"}, &inventory); err != nil {
		return err
	}
	if len(inventory.Data) != 1 || inventory.Data[0].Name != serverName {
		return errors.New("Новый чат не видит сервер kultura_os")
	}
	requests := []struct {
		name string
		args map[string]string
	}{
		{"common_whoami", map[string]string{}}, {"common_instructions", map[string]string{"domain": "all"}},
		{"common_docs_list", map[string]string{}}, {"common_bars_reference", map[string]string{}},
	}
	var account struct {
		Connector struct {
			Mode, Domain string
			Tools        int
			Hidden       int `json:"tools_hidden_by_mode"`
		}
	}
	for _, r := range requests {
		if _, ok := inventory.Data[0].Tools[r.name]; !ok {
			return fmt.Errorf("В чате отсутствует %s", r.name)
		}
		var reply struct {
			IsError bool
			Content []struct{ Text string }
		}
		if err := c.call("mcpServer/tool/call", map[string]any{"threadId": started.Thread.ID, "server": serverName, "tool": r.name, "arguments": r.args}, &reply); err != nil {
			return err
		}
		if reply.IsError || len(reply.Content) == 0 || reply.Content[0].Text == "" {
			return fmt.Errorf("Сервер не вернул данные для %s", r.name)
		}
		if r.name == "common_whoami" {
			if err := json.Unmarshal([]byte(reply.Content[0].Text), &account); err != nil {
				return fmt.Errorf("Ответ common_whoami: %w", err)
			}
			a := account.Connector
			if a.Mode != "full" || a.Domain != "all" || a.Tools <= 0 || a.Hidden != 0 {
				return fmt.Errorf("Вход выполнен. Сервер выдал режим %q и раздел %q. Полный доступ ко всем разделам не подтверждён", a.Mode, a.Domain)
			}
		}
	}
	fmt.Printf("Культура OS готова в локальном Codex. Полный доступ, инструментов %d. Инструкции и справочник баров загружены.\n", account.Connector.Tools)
	return nil
}

func run() error {
	exe, err := executable()
	if err != nil {
		return err
	}
	self, err := os.Executable()
	if err != nil {
		return err
	}
	bundle, err := zip.OpenReader(self)
	if err != nil {
		return err
	}
	defer bundle.Close()
	base, err := os.UserConfigDir()
	if err != nil {
		return err
	}
	root, err := unpack(bundle, filepath.Join(base, "KulturaOS", "marketplaces"))
	if err != nil {
		return err
	}
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Minute)
	defer cancel()
	if err := connect(ctx, exe); err != nil {
		return err
	}
	c, err := start(ctx, exe)
	if err != nil {
		return err
	}
	defer c.close()
	if err := registerMarketplace(c, root); err != nil {
		return err
	}
	if err := install(c, root); err != nil {
		return err
	}
	return checkThread(c, base)
}

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, "Установка остановлена:", err)
		if runtime.GOOS == "windows" {
			fmt.Print("Enter — закрыть окно.")
			bufio.NewReader(os.Stdin).ReadString('\n')
		}
		os.Exit(1)
	}
}

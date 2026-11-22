// Personal, local ChatGPT plugin installer. Communicates with the official local Codex app-server over stdio.
package main

import (
	"archive/zip"
	"bufio"
	"context"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"runtime"
	"strings"
	"time"
)

const directory = "https://chatgpt.com/plugins"
const endpoint = "https://beerkultura.ru/mcp"

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

var validID = regexp.MustCompile(`^(?:plugin_)?asdk_app_[A-Za-z0-9_-]+$`)

type app struct {
	ID, Name, InstallURL string
	IsAccessible         bool
	Branding             struct{ Website string }
}

func verified(a app) bool {
	u, err := url.Parse(a.Branding.Website)
	if err != nil || u.Scheme != "https" || !strings.EqualFold(u.Host, "beerkultura.ru") || u.User != nil {
		return false
	}
	if u.Path != "/mcp" && u.Path != "/plugins/kultura-os/support" {
		return false
	}
	switch strings.ToLower(strings.TrimSpace(a.Name)) {
	case "культура", "культура os", "kultura os", "beerkultura", "kultura":
		return a.IsAccessible && validID.MatchString(a.ID)
	}
	return false
}
func available(c *client) ([]app, error) {
	var list []app
	cursor := ""
	for {
		var page struct {
			Data       []app
			NextCursor string
		}
		args := map[string]any{"limit": 100, "forceRefetch": cursor == ""}
		if cursor != "" {
			args["cursor"] = cursor
		}
		if err := c.call("app/list", args, &page); err != nil {
			return nil, err
		}
		list = append(list, page.Data...)
		if page.NextCursor == "" {
			return list, nil
		}
		if page.NextCursor == cursor {
			return nil, errors.New("повтор страницы каталога")
		}
		cursor = page.NextCursor
	}
}

func readID(s string) (string, error) {
	s = strings.TrimSpace(s)
	if !validID.MatchString(s) {
		u, err := url.Parse(s)
		if err != nil || u.Scheme != "https" || u.Host != "chatgpt.com" || u.User != nil || !strings.HasPrefix(u.Path, "/plugins/") {
			return "", errors.New("Нужна ссылка на карточку ChatGPT или ID зарегистрированного MCP")
		}
		s = filepath.Base(strings.TrimSuffix(u.Path, "/"))
		if !validID.MatchString(s) {
			return "", errors.New("В ссылке отсутствует ID приложения MCP")
		}
	}
	return strings.TrimPrefix(s, "plugin_"), nil
}

func choose(list []app, input *bufio.Reader) (string, error) {
	var candidates []app
	for _, a := range list {
		if verified(a) {
			candidates = append(candidates, a)
		}
	}
	if len(candidates) == 1 {
		fmt.Println("Подключение найдено в текущем аккаунте:", candidates[0].Name)
		return candidates[0].ID, nil
	}
	fmt.Println("Откройте", directory, "в своём аккаунте и выберите подключение с адресом", endpoint)
	fmt.Println("Если такого подключения ещё нет, добавьте его через Add custom MCP server с OAuth.")
	fmt.Print("Вставьте ссылку на карточку или её технический ID (Enter для выхода): ")
	line, _ := input.ReadString('\n')
	if strings.TrimSpace(line) == "" {
		return "", errors.New("Подключение ещё не выбрано")
	}
	id, err := readID(line)
	if err != nil {
		return "", err
	}
	for _, a := range list {
		if strings.TrimPrefix(a.ID, "plugin_") == id {
			return a.ID, nil
		}
	}
	return id, nil
}

func materialize(archive *zip.ReadCloser, root, id string) (string, error) {
	if !validID.MatchString(id) {
		return "", errors.New("Некорректный ID MCP")
	}
	for _, f := range archive.File {
		if !filepath.IsLocal(filepath.FromSlash(f.Name)) {
			return "", errors.New("Неверный путь в пакете")
		}
		path := filepath.Join(root, filepath.FromSlash(f.Name))
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
		if f.Name == "plugins/kultura-os/.codex-plugin/plugin.json" {
			var m map[string]any
			if err = json.Unmarshal(data, &m); err != nil {
				return "", err
			}
			digest := sha256.Sum256([]byte(id))
			m["version"] = fmt.Sprintf("%s+local.%x", m["version"], digest[:6])
			if data, err = json.Marshal(m); err != nil {
				return "", err
			}
		}
		if err = os.WriteFile(path, data, 0600); err != nil {
			return "", err
		}
	}
	// Apps are declared in a Codex-compatible local manifest. The portable portal package stays separate.
	mapping, err := json.Marshal(map[string]any{"apps": map[string]any{"kultura": map[string]string{"id": id}}})
	if err != nil {
		return "", err
	}
	if err = os.WriteFile(filepath.Join(root, "plugins", "kultura-os", ".app.json"), mapping, 0600); err != nil {
		return "", err
	}
	return filepath.Join(root, ".agents", "plugins", "marketplace.json"), nil
}

type toolInfo struct {
	Name string
	Meta map[string]any `json:"_meta"`
}

func checkThread(c *client, root, id string) error {
	var started struct{ Thread struct{ ID string } }
	if err := c.call("thread/start", map[string]any{"cwd": root, "ephemeral": true}, &started); err != nil {
		return err
	}
	var status struct {
		Data []struct {
			Name  string
			Tools map[string]toolInfo
		}
	}
	params := map[string]any{"threadId": started.Thread.ID, "serverName": "codex_apps", "detail": "toolsAndAuthOnly"}
	if err := c.call("mcpServerStatus/list", params, &status); err != nil {
		return err
	}
	var names []string
	for _, server := range status.Data {
		if server.Name != "codex_apps" {
			continue
		}
		for key, t := range server.Tools {
			if !strings.HasSuffix(strings.ToLower(key), "common_whoami") {
				continue
			}
			// Accept only a tool tied to the selected connector. A native bearer server
			// or another app with a tool of the same name cannot verify this install.
			meta, _ := json.Marshal(t.Meta)
			aliases := []string{id, strings.TrimPrefix(id, "plugin_")}
			for _, alias := range aliases {
				if strings.Contains(key, alias) || strings.Contains(string(meta), fmt.Sprintf("%q", alias)) {
					names = append(names, key)
					break
				}
			}
		}
	}
	if len(names) != 1 {
		return errors.New("Пакет установлен. Клиент не показал однозначно привязанный common_whoami в каталоге приложений этой сессии; вызов из ChatGPT пока не подтверждён")
	}
	var reply struct {
		IsError bool
		Content []struct{ Text string }
	}
	if err := c.call("mcpServer/tool/call", map[string]any{"threadId": started.Thread.ID, "server": "codex_apps", "tool": names[0], "arguments": map[string]any{}}, &reply); err != nil {
		return err
	}
	if !reply.IsError {
		for _, b := range reply.Content {
			var data struct {
				Connector struct {
					Mode, Domain string
					Tools        int
				}
			}
			if json.Unmarshal([]byte(b.Text), &data) == nil && data.Connector.Mode != "" && data.Connector.Tools > 0 {
				fmt.Printf("common_whoami ответил через зарегистрированное приложение: режим %s, раздел %s, инструментов %d.\n", data.Connector.Mode, data.Connector.Domain, data.Connector.Tools)
				return nil
			}
		}
	}
	return errors.New("Клиент не получил ожидаемый ответ common_whoami")
}

func run(input *bufio.Reader) error {
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
		return fmt.Errorf("в установщике отсутствует пакет: %w", err)
	}
	defer bundle.Close()
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Minute)
	defer cancel()
	c, err := start(ctx, exe)
	if err != nil {
		return err
	}
	defer c.close()
	fmt.Println("Проверяю список подключений в вашем аккаунте через Codex…")
	list, err := available(c)
	if err != nil {
		fmt.Println("Список подключений недоступен:", err)
	}
	id, err := choose(list, input)
	if err != nil {
		return err
	}
	home, err := os.UserConfigDir()
	if err != nil {
		return err
	}
	parent := filepath.Join(home, "KulturaOS", "marketplaces")
	if err = os.MkdirAll(parent, 0700); err != nil {
		return err
	}
	root, err := os.MkdirTemp(parent, "local-")
	if err != nil {
		return err
	}
	market, err := materialize(bundle, root, id)
	if err != nil {
		return err
	}
	selection := map[string]string{"pluginName": "kultura-os", "marketplacePath": market}
	inspect := func(afterInstall bool) error {
		var info struct {
			Plugin struct {
				Summary struct{ Installed, Enabled bool }
				Apps    []app
				Skills  []json.RawMessage
			}
		}
		if err := c.call("plugin/read", selection, &info); err != nil {
			return err
		}
		if afterInstall && (!info.Plugin.Summary.Installed || !info.Plugin.Summary.Enabled) {
			return errors.New("Клиент не подтвердил, что плагин установлен и включён")
		}
		if len(info.Plugin.Apps) != 1 || info.Plugin.Apps[0].ID != id || len(info.Plugin.Skills) != 2 {
			return errors.New("Клиент не подтвердил привязку и оба навыка")
		}
		return nil
	}
	if err = inspect(false); err != nil {
		return err
	}
	var installed struct{ AppsNeedingAuth []app }
	if err = c.call("plugin/install", selection, &installed); err != nil {
		return err
	}
	if err = inspect(true); err != nil {
		return err
	}
	fmt.Println("Культура OS установлена. Codex прочитал привязку MCP и оба навыка.")
	if len(installed.AppsNeedingAuth) > 0 {
		fmt.Println("Клиент запросил авторизацию приложения в ChatGPT. Выберите «Подключить» в карточке зарегистрированного MCP.")
	}
	fmt.Println("Проверяю вызов common_whoami через подключение приложения…")
	return checkThread(c, root, id)
}
func main() {
	input := bufio.NewReader(os.Stdin)
	err := run(input)
	if err != nil {
		fmt.Fprintln(os.Stderr, "Остановлено:", err)
	}
	if runtime.GOOS == "windows" {
		fmt.Print("Enter — закрыть окно.")
		input.ReadString('\n')
	}
	if err != nil {
		os.Exit(1)
	}
}

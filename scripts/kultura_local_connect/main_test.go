package main

import (
	"bufio"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

// The actual installer is run with no user input; only the Codex subprocess is substituted.
func TestInstalledExecutable(t *testing.T) {
	installer := os.Getenv("KULTURA_QA_INSTALLER")
	if installer == "" {
		t.Skip("supply compiled installer")
	}
	for _, scenario := range []string{"fresh", "existing", "expired", "conflict", "read-only", "offline"} {
		t.Run(scenario, func(t *testing.T) {
			bin, user := t.TempDir(), t.TempDir()
			self, err := os.Executable()
			if err != nil {
				t.Fatal(err)
			}
			b, err := os.ReadFile(self)
			if err != nil {
				t.Fatal(err)
			}
			name := "codex"
			if runtime.GOOS == "windows" {
				name += ".exe"
			}
			if err = os.WriteFile(filepath.Join(bin, name), b, 0700); err != nil {
				t.Fatal(err)
			}
			t.Setenv("PATH", bin+string(os.PathListSeparator)+os.Getenv("PATH"))
			t.Setenv("KULTURA_QA_BACKEND", scenario)
			t.Setenv("KULTURA_QA_ROOT", user)
			t.Setenv("XDG_CONFIG_HOME", user)
			t.Setenv("AppData", user)
			cmd := exec.Command(installer)
			out, err := cmd.CombinedOutput()
			want := scenario == "fresh" || scenario == "existing" || scenario == "expired"
			if (err == nil) != want || strings.Contains(string(out), "инструментов 255") != want {
				t.Fatalf("%v %s", err, out)
			}
			if want {
				if _, err := os.Stat(filepath.Join(user, "called-common_bars_reference")); err != nil {
					t.Fatal(err)
				}
			}
		})
	}
}

func TestMain(m *testing.M) {
	scenario := os.Getenv("KULTURA_QA_BACKEND")
	if scenario == "" || len(os.Args) < 2 {
		os.Exit(m.Run())
	}
	dir := os.Getenv("KULTURA_QA_ROOT")
	switch os.Args[1] {
	case "mcp":
		args := strings.Join(os.Args[2:], " ")
		switch args {
		case "list --json":
			if scenario == "fresh" {
				fmt.Println("[]")
				return
			}
			url := endpoint
			auth := "o_auth"
			if scenario == "expired" {
				auth = "not_logged_in"
			}
			if scenario == "conflict" {
				url = "https://unrelated.invalid/mcp"
			}
			json.NewEncoder(os.Stdout).Encode([]any{map[string]any{"name": serverName, "enabled": true, "auth_status": auth, "transport": map[string]string{"type": "streamable_http", "url": url}}})
		case "add " + serverName + " --url " + endpoint:
			if scenario != "fresh" {
				panic("unexpected registration")
			}
			os.Exit(0)
		case "login " + serverName:
			if scenario != "expired" {
				panic("unexpected login")
			}
			os.Exit(0)
		default:
			panic(args)
		}
	case "app-server":
		in := bufio.NewScanner(os.Stdin)
		enc := json.NewEncoder(os.Stdout)
		installed := false
		for in.Scan() {
			var req struct {
				ID     int
				Method string
				Params map[string]any
			}
			if err := json.Unmarshal(in.Bytes(), &req); err != nil {
				panic(err)
			}
			var result any = map[string]any{}
			switch req.Method {
			case "initialized":
				continue
			case "initialize", "config/read", "marketplace/add":
			case "plugin/install":
				installed = true
			case "plugin/read":
				path := filepath.Join(filepath.Dir(req.Params["marketplacePath"].(string)), "..", "..", "plugins", "kultura-os")
				for _, f := range []string{".codex-plugin/plugin.json", ".mcp.json", "skills/setup/SKILL.md", "skills/kultura-os/SKILL.md"} {
					if _, err := os.Stat(filepath.Join(path, f)); err != nil {
						panic(err)
					}
				}
				data, err := os.ReadFile(filepath.Join(path, ".mcp.json"))
				if err != nil {
					panic(err)
				}
				var cfg struct {
					McpServers map[string]struct{ URL string }
				}
				if json.Unmarshal(data, &cfg) != nil || cfg.McpServers[serverName].URL != endpoint {
					panic("invalid endpoint")
				}
				result = map[string]any{"plugin": map[string]any{"mcpServers": []string{serverName}, "skills": []string{"setup", "kultura-os"}, "summary": map[string]bool{"installed": installed, "enabled": true}}}
			case "thread/start":
				result = map[string]any{"thread": map[string]string{"id": "fixture"}}
			case "mcpServerStatus/list":
				if req.Params["serverName"] != serverName {
					panic("wrong server")
				}
				tools := map[string]any{}
				if scenario != "offline" {
					for _, n := range []string{"common_whoami", "common_instructions", "common_docs_list", "common_bars_reference"} {
						tools[n] = map[string]any{}
					}
				}
				result = map[string]any{"data": []any{map[string]any{"name": serverName, "tools": tools}}}
			case "mcpServer/tool/call":
				if req.Params["threadId"] != "fixture" || req.Params["server"] != serverName {
					panic("wrong call")
				}
				name := req.Params["tool"].(string)
				body := "test"
				if name == "common_whoami" {
					mode := "full"
					if scenario == "read-only" {
						mode = "read"
					}
					body = fmt.Sprintf(`{"connector":{"domain":"all","mode":%q,"tools":255,"tools_hidden_by_mode":0}}`, mode)
				}
				if err := os.WriteFile(filepath.Join(dir, "called-"+name), nil, 0600); err != nil {
					panic(err)
				}
				result = map[string]any{"content": []any{map[string]string{"text": body}}}
			default:
				panic("unexpected RPC " + req.Method)
			}
			if err := enc.Encode(map[string]any{"id": req.ID, "result": result}); err != nil {
				panic(err)
			}
		}
	default:
		panic(os.Args[1])
	}
}

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

const fixtureID = "asdk_app_0123456789abcdef"

func TestLink(t *testing.T) {
	for _, s := range []string{fixtureID, "plugin_" + fixtureID, "https://chatgpt.com/plugins/example/plugin_" + fixtureID} {
		id, err := readID(s)
		if err != nil || id != fixtureID {
			t.Fatal(s, id, err)
		}
	}
	for _, s := range []string{"https://beerkultura.ru/oauth/authorize?state=opaque", "https://chatgpt.com.evil.invalid/plugins/" + fixtureID, "https://chatgpt.com/plugins", ""} {
		if _, err := readID(s); err == nil {
			t.Fatal("unexpected ID", s)
		}
	}
}

func TestInstalledExecutable(t *testing.T) {
	installer := os.Getenv("KULTURA_QA_INSTALLER")
	if installer == "" {
		t.Skip("supply compiled installer")
	}
	for _, scenario := range []string{"works", "unrelated", "missing"} {
		t.Run(scenario, func(t *testing.T) {
			bin := t.TempDir()
			user := t.TempDir()
			self, err := os.Executable()
			if err != nil {
				t.Fatal(err)
			}
			cli := "codex"
			if runtime.GOOS == "windows" {
				cli += ".exe"
			}
			// Test executable doubles as an isolated local app-server; no account, network or user profile is used.
			b, err := os.ReadFile(self)
			if err != nil {
				t.Fatal(err)
			}
			if err = os.WriteFile(filepath.Join(bin, cli), b, 0700); err != nil {
				t.Fatal(err)
			}
			t.Setenv("PATH", bin+string(os.PathListSeparator)+os.Getenv("PATH"))
			t.Setenv("KULTURA_QA_BACKEND", scenario)
			t.Setenv("XDG_CONFIG_HOME", user)
			t.Setenv("AppData", user)
			cmd := exec.Command(installer)
			cmd.Stdin = strings.NewReader("\n\n")
			out, err := cmd.CombinedOutput()
			if scenario == "works" {
				if err != nil || !strings.Contains(string(out), "инструментов 255") {
					t.Fatalf("%v %s", err, out)
				}
			} else {
				if err == nil || strings.Contains(string(out), "инструментов 255") {
					t.Fatalf("%v %s", err, out)
				}
			}
		})
	}
}

func TestMain(m *testing.M) {
	scenario := os.Getenv("KULTURA_QA_BACKEND")
	if len(os.Args) != 2 || os.Args[1] != "app-server" || scenario == "" {
		os.Exit(m.Run())
	}
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
		case "initialize":
		case "app/list":
			apps := []any{}
			if scenario != "missing" {
				apps = append(apps, map[string]any{"name": "Культура OS", "id": fixtureID, "isAccessible": true, "branding": map[string]string{"website": endpoint}})
			}
			result = map[string]any{"data": apps}
		case "plugin/install":
			installed = true
		case "plugin/read":
			root := filepath.Clean(filepath.Join(req.Params["marketplacePath"].(string), "../../..", "plugins", "kultura-os"))
			mp, err := os.ReadFile(filepath.Join(root, ".app.json"))
			if err != nil {
				panic(err)
			}
			var d struct{ Apps map[string]app }
			if err = json.Unmarshal(mp, &d); err != nil || d.Apps["kultura"].ID != fixtureID {
				panic("bad binding")
			}
			for _, f := range []string{".codex-plugin/plugin.json", ".mcp.json", "skills/setup/SKILL.md", "skills/kultura-os/SKILL.md"} {
				if _, err = os.Stat(filepath.Join(root, f)); err != nil {
					panic(err)
				}
			}
			result = map[string]any{"plugin": map[string]any{"skills": []any{"setup", "kultura-os"}, "apps": []app{d.Apps["kultura"]}, "summary": map[string]any{"installed": installed, "enabled": installed}}}
		case "thread/start":
			result = map[string]any{"thread": map[string]string{"id": "thread-fixture"}}
		case "mcpServerStatus/list":
			owner := fixtureID
			if scenario == "unrelated" {
				owner = "asdk_app_unrelated"
			}
			result = map[string]any{"data": []any{map[string]any{"name": "codex_apps", "tools": map[string]any{"kultura_common_whoami": map[string]any{"_meta": map[string]string{"connector_id": owner}}}}}}
		case "mcpServer/tool/call":
			if !installed || req.Params["server"] != "codex_apps" || req.Params["tool"] != "kultura_common_whoami" || req.Params["threadId"] != "thread-fixture" {
				panic("wrong tool call")
			}
			result = map[string]any{"content": []any{map[string]string{"text": `{"connector":{"mode":"full","domain":"all","tools":255}}`}}}
		default:
			panic(fmt.Sprintf("unexpected method %q", req.Method))
		}
		if err := enc.Encode(map[string]any{"id": req.ID, "result": result}); err != nil {
			panic(err)
		}
	}
	os.Exit(0)
}

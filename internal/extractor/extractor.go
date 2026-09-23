// Copyright 2026 Oliver R. Calazans Jeronimo
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

package extractor

import (
	"context"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strings"

	"gitbleed/internal/argparser"
	"gitbleed/internal/display"
	"gitbleed/internal/valid"
	"gitbleed/internal/workers"
)

var errStopSuccess = errors.New("stop requested")



type Extractor struct {
	args   *argparser.Arguments
	client *workers.Client
	head   *http.Response
}



func New(args *argparser.Arguments) *Extractor {
	return &Extractor{args: args}
}



func (l *Extractor) Execute(ctx context.Context) error {
	l.checkOutputDir()
	l.client = workers.NewClient(l.args)

	if err := l.findBaseURL();                err != nil { return err }
	if err := l.tryToConnect(ctx);            err != nil { return err }
	if err := l.validResponse();              err != nil { return err }
	if err := l.tryFastDump(ctx);             err != nil { return err }
	if err := l.fetchCommonFiles(ctx);        err != nil { return err }
	if err := l.discoverReferences(ctx);      err != nil { return err }
	if err := l.fetchGitPacks(ctx);           err != nil { return err }
	if err := l.discoverAndFetchObjects(ctx); err != nil { return err }
	if err := l.finalizeCheckout();           err != nil { return err }

	return nil
}



func (l *Extractor) checkOutputDir() {
	entries, err := os.ReadDir(l.args.Directory)

	if err == nil && len(entries) > 0 {
		msg := fmt.Sprintf("Destination '%s' is not empty", l.args.Directory)
		display.Warning(msg)
	}
}




func (l *Extractor) findBaseURL() error {
	url := strings.TrimRight(l.args.URL, "/")
	url  = strings.TrimSuffix(url, "HEAD")
	url  = strings.TrimRight(url, "/")
	url  = strings.TrimSuffix(url, ".git")

	l.args.URL = strings.TrimRight(url, "/")
	
	return nil
}



var headPattern = regexp.MustCompile(`^(ref:.*|[0-9a-f]{40}$)`)

func (l *Extractor) validResponse() error {
	if l.head == nil {
		return errors.New("no HEAD response")
	}
	defer l.head.Body.Close()

	ok, _, msg := valid.VerifyResponse(l.head)

	switch {
	case l.head.StatusCode >= 400:
		return errors.New("target unreachable, dumping stopped")

	case l.head.StatusCode >= 300:
		display.Warning(fmt.Sprintf("Redirection required to %s", l.head.Header.Get("Location")))
		return errStopSuccess
	
	case !ok:
		return fmt.Errorf("invalid response from %s: %s", l.head.Request.URL, msg)
	}

	body, err := io.ReadAll(l.head.Body)
	if err != nil {
		return err
	}

	if !headPattern.Match(body) {
		return fmt.Errorf("%s is not a git HEAD file", l.head.Request.URL)
	}
	
	return nil
}



func (l *Extractor) finalizeCheckout() error {
	display.Section("Running git checkout")

	l.sanitizeConfig(filepath.Join(l.args.Directory, ".git", "config"))

	cmd := exec.Command("git", "-C", l.args.Directory, "checkout", ".")
	cmd.Stderr = nil
	cmd.Stdout = nil
	_ = cmd.Run()
	return nil
}



var unsafeConfig = regexp.MustCompile(`(?im)^\s*(fsmonitor|sshcommand|askpass|editor|pager)`)

func (l *Extractor) sanitizeConfig(path string) {
	data, err := os.ReadFile(path)
	if err != nil {
		display.Warning(".git/config not found")
		return
	}

	display.Section("Sanitizing .git/config")

	out := unsafeConfig.ReplaceAll(data, []byte("# $0"))
	if string(out) != string(data) {
		display.Warning(fmt.Sprintf("'%s' file was altered", path))
		_ = os.WriteFile(path, out, 0o644)
	}
}
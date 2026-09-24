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
	"fmt"
	"gitbleed/internal/check"
	"gitbleed/internal/display"
	"gitbleed/internal/gitx"
	"gitbleed/internal/valid"
	"gitbleed/internal/workers"
	"os"
	"path/filepath"
	"regexp"
)



func (l *Extractor) tryToConnect(ctx context.Context) error {
	resp, err := l.client.Get(ctx, l.args.URL + "/.git/HEAD", true)
	
	if err != nil {
		return fmt.Errorf("unable to connect to %s: %s", l.args.URL, err.Error())
	}
	
	l.head = resp
	
	return nil
}



func (l *Extractor) tryFastDump(ctx context.Context) error {
	display.Section("Trying fast dumping")

	resp, err := l.client.Get(ctx, l.args.URL+"/.git/", false)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode != 200 || !check.IsHTML(resp) {
		return nil
	}

	files, err := valid.GetIndexedFiles(resp)
	if err != nil {
		return err
	}

	hasHead := false
	for _, f := range files {
		if f == "HEAD" || f == "./HEAD" {
			hasHead = true
			break
		}
	}
	
	if !hasHead {
		return nil
	}

	display.Section("Fetching .git recursively")
	workers.RunTasks(
		ctx, l.args.Jobs, []string{".git/", ".gitignore"},
		workers.RecursiveDownloadWorker(l.client, l.args),
	)

	if err := l.finalizeCheckout(); err != nil {
		return err
	}

	return errStopSuccess
}



func (l *Extractor) fetchCommonFiles(ctx context.Context) error {
	display.Section("Fetching common files")

	tasks := []string{
		".gitignore",
		".git/COMMIT_EDITMSG",
		".git/description",
		".git/hooks/applypatch-msg.sample",
		".git/hooks/commit-msg.sample",
		".git/hooks/post-commit.sample",
		".git/hooks/post-receive.sample",
		".git/hooks/post-update.sample",
		".git/hooks/pre-applypatch.sample",
		".git/hooks/pre-commit.sample",
		".git/hooks/pre-push.sample",
		".git/hooks/pre-rebase.sample",
		".git/hooks/pre-receive.sample",
		".git/hooks/prepare-commit-msg.sample",
		".git/hooks/update.sample",
		".git/index",
		".git/info/exclude",
		".git/objects/info/packs",
	}

	workers.RunTasks(
		ctx, l.args.Jobs, tasks,
		workers.DownloadWorker(l.client, l.args),
	)

	return nil
}



func (l *Extractor) discoverReferences(ctx context.Context) error {
	display.Section("Finding refs/")

	tasks := []string{
		".git/FETCH_HEAD", ".git/HEAD", ".git/ORIG_HEAD", ".git/config",
		".git/info/refs", ".git/logs/HEAD", ".git/packed-refs", ".git/refs/stash",
		".git/logs/refs/stash",
	}

	defaults := []string{"main", "master", "staging", "production", "development"}
	for _, b := range defaults {
		tasks = append(tasks,
			".git/logs/refs/heads/"+b,
			".git/refs/heads/"+b,
			".git/logs/refs/remotes/origin/"+b,
			".git/refs/remotes/origin/"+b,
			".git/refs/wip/wtree/refs/heads/"+b,
			".git/refs/wip/index/refs/heads/"+b,
		)
	}

	tasks = append(tasks,
		".git/logs/refs/remotes/origin/HEAD",
		".git/refs/remotes/origin/HEAD",
	)

	l.addUserBranches(&tasks)

	workers.RunTasks(
		ctx, l.args.Jobs, tasks,
		workers.FindRefsWorker(l.client, l.args),
	)

	return nil
}



func (l *Extractor) addUserBranches(tasks *[]string) {
	valid := regexp.MustCompile(`^[A-Za-z0-9\-\._]+$`)
	
	for _, b := range l.args.Branches {
	
		if !valid.MatchString(b) {
			display.Warning(fmt.Sprintf("Ignoring invalid branch name '%s'", b))
			continue
		}
	
		*tasks = append(*tasks,
			".git/logs/refs/heads/"+b,
			".git/refs/heads/"+b,
			".git/logs/refs/remotes/origin/"+b,
			".git/refs/remotes/origin/"+b,
			".git/refs/wip/wtree/refs/heads/"+b,
			".git/refs/wip/index/refs/heads/"+b,
		)
	}
}



func (l *Extractor) fetchGitPacks(ctx context.Context) error {
	display.Section("Finding packs")

	infoPath  := filepath.Join(l.args.Directory, ".git", "objects", "info", "packs")
	data, err := os.ReadFile(infoPath)
	
	if err != nil {
		return nil
	}

	var tasks []string
	re := regexp.MustCompile(`pack-([a-f0-9]{40})\.pack`)

	for _, m := range re.FindAllStringSubmatch(string(data), -1) {
		tasks = append(tasks,
			".git/objects/pack/pack-"+m[1]+".idx",
			".git/objects/pack/pack-"+m[1]+".pack",
		)
	}

	workers.RunTasks(
		ctx, l.args.Jobs, tasks,
		workers.DownloadWorker(l.client, l.args),
	)

	return nil
}



func (l *Extractor) discoverAndFetchObjects(ctx context.Context) error {
	display.Section("Finding objects")

	objs   := make(map[string]struct{})
	packed := make(map[string]struct{})

	files := []string{
		filepath.Join(l.args.Directory, ".git", "packed-refs"),
		filepath.Join(l.args.Directory, ".git", "info", "refs"),
		filepath.Join(l.args.Directory, ".git", "FETCH_HEAD"),
		filepath.Join(l.args.Directory, ".git", "ORIG_HEAD"),
	}

	collectFromGitDir(&files, filepath.Join(l.args.Directory, ".git", "refs"))
	collectFromGitDir(&files, filepath.Join(l.args.Directory, ".git", "logs"))
	extractSHA1FromFiles(files, objs)
	gitx.ParseStagingArea(filepath.Join(l.args.Directory, ".git", "index"), objs)
	gitx.ProcessPackFiles(filepath.Join(l.args.Directory, ".git", "objects", "pack"), packed, objs)

	display.Section("Fetching objects")

	tasks := make([]string, 0, len(objs))
	for o := range objs {
		if _, ok := packed[o]; ok {
			continue
		}

		tasks = append(tasks, o)
	}

	workers.RunTasks(
		ctx, l.args.Jobs, tasks,
		workers.FindObjectsWorker(l.client, l.args),
	)

	return nil
}
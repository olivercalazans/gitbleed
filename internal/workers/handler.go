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

package workers

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"strings"

	"gitbleed/internal/argparser"
	"gitbleed/internal/display"
	"gitbleed/internal/fsutils"
	"gitbleed/internal/gitx"
	"gitbleed/internal/valid"
)



func DownloadWorker(client *Client, args *argparser.Arguments) TaskFunc {
	return func(ctx context.Context, task string) ([]string, error) {
		return downloadOne(ctx, client, args, task)
	}
}



func RecursiveDownloadWorker(client *Client, args *argparser.Arguments) TaskFunc {
	return func(ctx context.Context, task string) ([]string, error) {
		return downloadRecursive(ctx, client, args, task)
	}
}



func FindRefsWorker(client *Client, args *argparser.Arguments) TaskFunc {
	return func(ctx context.Context, task string) ([]string, error) {
		return findRefs(ctx, client, args, task)
	}
}



func FindObjectsWorker(client *Client, args *argparser.Arguments) TaskFunc {
	return func(ctx context.Context, task string) ([]string, error) {
		return findObject(ctx, client, args, task)
	}
}




func downloadOne(ctx context.Context, c *Client, args *argparser.Arguments, task string) ([]string, error) {
	abspath := filepath.Join(args.Directory, filepath.FromSlash(task))

	if _, err := os.Stat(abspath); err == nil {
		fmt.Printf("[---] Already downloaded %s/%s\n", args.URL, task)
		return nil, nil
	}

	resp, err := c.Get(ctx, args.URL+"/"+task, false)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	ok, show, msg := valid.VerifyResponse(resp)

	if !ok {
		if show {
			display.Warning(fmt.Sprintf("Invalid response from %s: %s", resp.Request.URL, msg))
		}

		return nil, nil
	}

	return nil, writeBody(abspath, resp.Body)
}



func downloadRecursive(ctx context.Context, c *Client, args *argparser.Arguments, task string) ([]string, error) {
	abspath := filepath.Join(args.Directory, filepath.FromSlash(task))

	if _, err := os.Stat(abspath); err == nil {
		fmt.Printf("[---] Already downloaded %s/%s\n", args.URL, task)
		return nil, nil
	}

	resp, err := c.Get(ctx, args.URL+"/"+task, false)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	display.Response(resp)

	if (resp.StatusCode == http.StatusMovedPermanently || resp.StatusCode == http.StatusFound) &&
		strings.HasSuffix(resp.Header.Get("Location"), task+"/") {
		return []string{task + "/"}, nil
	}

	if strings.HasSuffix(task, "/") {
		files, err := valid.GetIndexedFiles(resp)
		if err != nil {
			return nil, err
		}

		out := make([]string, 0, len(files))
		for _, f := range files {
			out = append(out, task+f)
		}

		return out, nil
	}

	ok, show, msg := valid.VerifyResponse(resp)
	if !ok {
		if show {
			display.Warning(fmt.Sprintf("Invalid response from %s: %s", resp.Request.URL, msg))
		}

		return nil, nil
	}

	return nil, writeBody(abspath, resp.Body)
}



var refRegex = regexp.MustCompile(`(refs(/[a-zA-Z0-9\-\._*]+)+)`)

func findRefs(ctx context.Context, c *Client, args *argparser.Arguments, task string) ([]string, error) {
	resp, err := c.Get(ctx, args.URL+"/"+task, false)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	ok, show, msg := valid.VerifyResponse(resp)
	if !ok {
		if show {
			display.Warning(fmt.Sprintf("Invalid response from %s: %s", resp.Request.URL, msg))
		}

		return nil, nil
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}

	abspath := filepath.Join(args.Directory, filepath.FromSlash(task))
	if err := fsutils.CreateIntermediateDirs(abspath); err != nil {
		return nil, err
	}

	if err := os.WriteFile(abspath, body, 0o644); err != nil {
		return nil, err
	}

	var tasks []string
	for _, m := range refRegex.FindAllStringSubmatch(string(body), -1) {
		ref := m[1]

		if strings.HasSuffix(ref, "*") || !valid.IsSafePath(ref) {
			continue
		}

		tasks = append(tasks, ".git/"+ref, ".git/logs/"+ref)
	}

	return tasks, nil
}



func findObject(ctx context.Context, c *Client, args *argparser.Arguments, task string) ([]string, error) {
	if len(task) != 40 {
		return nil, fmt.Errorf("invalid object hash: %q", task)
	}

	rel     := fmt.Sprintf(".git/objects/%s/%s", task[:2], task[2:])
	abspath := filepath.Join(args.Directory, filepath.FromSlash(rel))

	if _, err := os.Stat(abspath); err == nil {
		fmt.Printf("[---] Already downloaded %s/%s\n", args.URL, rel)
	} else {
		ok, err := fetchObject(ctx, c, args, rel, abspath)
		if err != nil { return nil, err }
		if !ok { return nil, nil }
	}

	obj, err := gitx.ParseLooseObject(abspath)
	if err != nil {
		display.Warning(fmt.Sprintf("Error while parsing file %s: %v", rel, err))
		return nil, nil
	}

	hashes, err := gitx.ReferencedSHA1(obj)
	if err != nil {
		display.Warning(fmt.Sprintf("Error while reading references of %s: %v", rel, err))
		return nil, nil
	}

	out := make([]string, 0, len(hashes))
	for _, h := range hashes {
		out = append(out, h.String())
	}
	
	return out, nil
}



func fetchObject(ctx context.Context, c *Client, args *argparser.Arguments, rel, abspath string) (bool, error) {
	resp, err := c.Get(ctx, args.URL+"/"+rel, false)
	if err != nil {
		return false, err
	}
	defer resp.Body.Close()

	ok, show, msg := valid.VerifyResponse(resp)
	if !ok {
		if show {
			display.Warning(fmt.Sprintf("Invalid response from %s: %s", resp.Request.URL, msg))
		}

		return false, nil
	}

	if err := writeBody(abspath, resp.Body); err != nil {
		return false, err
	}

	return true, nil
}



func writeBody(abspath string, body io.Reader) error {
	if err := fsutils.CreateIntermediateDirs(abspath); err != nil {
		return err
	}

	f, err := os.Create(abspath)
	if err != nil {
		return err
	}
	defer f.Close()

	_, err = io.Copy(f, body)
	return err
}
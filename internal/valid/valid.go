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

package valid

import (
	"fmt"
	"gitbleed/internal/check"
	"gitbleed/internal/display"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"strings"

	"golang.org/x/net/html"
)



func IsSafePath(path string) bool {
	if strings.HasPrefix(path, "/") {
		return false
	}

	home, err := os.UserHomeDir()
	if err != nil {
		return false
	}

	homeReal, err := filepath.EvalSymlinks(home)
	if err != nil {
		homeReal = home
	}

	joined := filepath.Join(homeReal, path)

	real, err := filepath.EvalSymlinks(joined)
	if err != nil {
		real = filepath.Clean(joined)
	}

	rel, err := filepath.Rel(homeReal, real)
	if err != nil {
		return false
	}

	if rel == ".." || strings.HasPrefix(rel, ".."+string(filepath.Separator)) {
		return false
	}

	return true
}



func GetIndexedFiles(resp *http.Response) ([]string, error) {
	doc, err := html.Parse(resp.Body)
	if err != nil {
		return nil, err
	}

	var files []string

	var walk func(*html.Node)
	walk = func(n *html.Node) {
		if n.Type == html.ElementNode && n.Data == "a" {
			for _, attr := range n.Attr {
				if attr.Key != "href" {
					continue
				}

				u, err := url.Parse(attr.Val)
				if err != nil {
					continue
				}

				if u.Path != "" &&
					IsSafePath(u.Path) &&
					u.Scheme == "" &&
					u.Host == "" {
					files = append(files, u.Path)
				}
			}
		}

		for c := n.FirstChild; c != nil; c = c.NextSibling {
			walk(c)
		}
	}

	walk(doc)

	return files, nil
}




func VerifyResponse(resp *http.Response) (valid bool, showMsg bool, errorMsg string) {
	display.Response(resp)

	if resp.StatusCode >= 400 {
		return false, false, ""
	}

	if resp.StatusCode >= 300 {
		if loc := resp.Header.Get("Location"); loc != "" {
			return false, true, fmt.Sprintf("Moved to %s. Code %d", loc, resp.StatusCode)
		}
	}

	if resp.Header.Get("Content-Length") == "0" {
		return false, true, "Responded with a zero-length body"
	}

	if check.IsHTML(resp) {
		urlStr := ""
		if resp.Request != nil {
			urlStr = resp.Request.URL.String()
		}

		return false, true, fmt.Sprintf("%s responded with a HTML", urlStr)
	}

	return true, false, ""
}
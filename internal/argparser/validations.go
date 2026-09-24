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

package argparser

import (
	"fmt"
	"gitbleed/internal/fsutils"
	"os"
	"regexp"
	"strings"
)



func (ap *ArgParser) validURL() error {
	if ap.filePath != "" {
		return nil
	}
	
	if ap.url == "" {
		return fmt.Errorf("--url is required")
	}

	return nil
}



func (ap *ArgParser) validHeaders() (map[string]string, error) {
	httpHeaders := map[string]string{
		"User-Agent": "curl/8.14.1",
		"Accept":     "*/*",
	}

	if len(ap.headers) == 0 {
		return httpHeaders, nil
	}

	for _, header := range ap.headers {
		tokens := strings.SplitN(header, "=", 2)
		if len(tokens) != 2 {
			return nil, fmt.Errorf("HTTP header must have the form NAME=VALUE, got %s", header)
		}

		name  := strings.TrimSpace(tokens[0])
		value := strings.TrimSpace(tokens[1])

		httpHeaders[name] = value
	}

	return httpHeaders, nil
}



func (ap *ArgParser) validJobs() error {
	if ap.jobs < 1 {
		return fmt.Errorf("Invalid number of jobs, got %d", ap.jobs)
	}

	return nil
}



func (ap *ArgParser) validRetry() error {
	if ap.retry < 1 {
		return fmt.Errorf("Invalid number of retries, got %d", ap.retry)
	}

	return nil
}



func (ap *ArgParser) validTimeout() error {
	if ap.timeout < 1 {
		return fmt.Errorf("Invalid timeout, got %d", ap.timeout)
	}

	return nil
}



func (ap *ArgParser) validDelay() error {
	if ap.delay < 0 {
		return fmt.Errorf("Delay value cannot be negative. Got %v", ap.delay)
	}

	return nil
}



func (ap *ArgParser) validProxy() error {
	if ap.proxy == "" {
		return nil
	}

	patterns := []*regexp.Regexp{
		regexp.MustCompile(`^socks5:(.*):(\d+)$`),
		regexp.MustCompile(`^socks4:(.*):(\d+)$`),
		regexp.MustCompile(`^http://(.*):(\d+)$`),
		regexp.MustCompile(`^(.*):(\d+)$`),
	}

	for _, re := range patterns {
		if re.MatchString(ap.proxy) {
			return nil
		}
	}

	return fmt.Errorf("Invalid proxy, got %s", ap.proxy)
}



func (ap *ArgParser) validFilePath() error {
	if ap.filePath == "" {
		return nil
	}

	urls, err := fsutils.ReadLines(ap.filePath)
	
	if err != nil {
		return err
	}

	ap.urlList = urls

	return nil
}



func (ap *ArgParser) createDir() error {
	if ap.filePath != "" {
		return nil
	}

	if ap.directory == "" {
		return fmt.Errorf("-o/--out is required")
	}

	if _, err := os.Stat(ap.directory); os.IsNotExist(err) {
		if err := os.MkdirAll(ap.directory, 0755); err != nil {
			return err
		}
	}

	info, err := os.Stat(ap.directory)
	if err != nil {
		return err
	}

	if !info.IsDir() {
		return fmt.Errorf("%s is not a directory", ap.directory)
	}

	return nil
}
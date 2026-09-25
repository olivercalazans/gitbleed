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
	"strings"
)



func (ap *ArgParser) validFilePath() []string {
	if ap.filePath == "" {
		return nil
	}

	urls, err := fsutils.ReadLines(ap.filePath)
	
	if err != nil {
		ap.addErr(err)
	}

	return urls
}



func (ap *ArgParser) validURL() string {
	if ap.filePath != "" {
		return ""
	}
	
	if ap.url == "" {
		ap.addErr(fmt.Errorf("--url or -f/--file required"))
	}

	return ap.url
}



func (ap *ArgParser) validHeaders() map[string]string {
	if len(ap.headers) == 0 {
		return map[string]string{
			"User-Agent": "curl/8.14.1",
			"Accept":     "*/*",
		}
	}

	httpHeaders := map[string]string{}

	for _, header := range ap.headers {
		tokens := strings.SplitN(header, "=", 2)
		if len(tokens) != 2 {
			err := fmt.Errorf("HTTP header must have the form NAME=VALUE, got %s", header)
			ap.errList = append(ap.errList, err)
			return nil
		}

		name  := strings.TrimSpace(tokens[0])
		value := strings.TrimSpace(tokens[1])

		httpHeaders[name] = value
	}

	return httpHeaders
}



func (ap *ArgParser) validJobs() int {
	if ap.jobs < 1 {
		ap.addErr(fmt.Errorf("Invalid number of jobs, got %d", ap.jobs))
	}

	return ap.jobs
}



func (ap *ArgParser) validRetry() int {
	if ap.retry < 1 {
		ap.addErr(fmt.Errorf("Invalid number of retries, got %d", ap.retry))
	}

	return ap.retry
}



func (ap *ArgParser) validTimeout() int {
	if ap.timeout < 1 {
		ap.addErr(fmt.Errorf("Invalid timeout, got %d", ap.timeout))
	}

	return ap.timeout
}



func (ap *ArgParser) validDelay() float64 {
	if ap.delay < 0 {
		ap.addErr(fmt.Errorf("Delay value cannot be negative. Got %v", ap.delay))
	}

	return ap.delay
}



func (ap *ArgParser) createDir() string {
	if ap.filePath != "" {
		return ""
	}

	if ap.directory == "" {
		ap.addErr(fmt.Errorf("-o/--out is required"))
		return ""
	}

	if _, err := os.Stat(ap.directory); os.IsNotExist(err) {
		if err := os.MkdirAll(ap.directory, 0755); err != nil {
			ap.addErr(err)
			return ""
		}
	}

	info, err := os.Stat(ap.directory)
	if err != nil {
		ap.addErr(err)
		return ""
	}

	if !info.IsDir() {
		ap.addErr(fmt.Errorf("%s is not a directory", ap.directory))
		return ""
	}

	return ap.directory
}
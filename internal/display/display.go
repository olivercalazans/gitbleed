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

package display

import (
	"fmt"
	"gitbleed/internal/check"
	"net/http"
	"os"
)



const (
	esc    = "\x1b"
	reset  = esc + "[0m"
	red    = esc + "[31m"
	yellow = esc + "[33m"
	green  = esc + "[32m"
	blue   = esc + "[34m"
)

const htmlTag = " [" + blue + "HTML" + reset + "] "



func Response(resp *http.Response) {
	code := resp.StatusCode

	var status string
	switch {
	case code >= 400 : status = fmt.Sprintf("%s%d%s", red, code, reset)
	case code >= 300 : status = fmt.Sprintf("%s%d%s", yellow, code, reset)
	case code >= 200 : status = fmt.Sprintf("%s%d%s", green, code, reset)
	default          : status = fmt.Sprintf("%d", code)
	}

	tag := " "
	if check.IsHTML(resp) {
		tag = htmlTag
	}

	url := ""
	if resp.Request != nil {
		url = resp.Request.URL.String()
	}

	fmt.Printf("[%s]%s%s\n", status, tag, url)
}



func Section(text string) {
	fmt.Printf("[###] %s\n", text)
}



func Warning(text string) {
	fmt.Printf("[%s!!!%s] %s\n", yellow, reset, text)
}



func Fatal(err error) {
	fmt.Fprintf(os.Stderr, "[%sERR%s] %s\n", red, reset, err.Error())
	os.Exit(1)
}



func FormatOnly200(resp *http.Response) (string, bool) {
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return "", false
	}

	status := fmt.Sprintf("%s%d%s", green, resp.StatusCode, reset)
	
	tag := " "
	if check.IsHTML(resp) {
		tag = htmlTag
	}

	url := ""
	if resp.Request != nil {
		url = resp.Request.URL.String()
	}

	return fmt.Sprintf("[%s]%s%s", status, tag, url), true
}
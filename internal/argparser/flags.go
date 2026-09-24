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
	"os"

	"github.com/spf13/pflag"
)



type Arguments struct {
	ClientCertP12Password string
	ClientCertP12         string
	Directory             string
	Proxy                 string
	URL                   string
	URLList               []string
	Jobs                  int
	Retry                 int
	Timeout               int
	HTTPHeaders           map[string]string
	Branches              []string
	Delay                 float64
	OnlyCheck             bool
}



func (ap *ArgParser) createArgs() {
	ap.parser = pflag.NewFlagSet("gitlooter", pflag.ContinueOnError)
	ap.parser.SortFlags = false
	ap.parser.SetInterspersed(true)

	ap.parser.Usage = func() {
		fmt.Fprintf(os.Stderr, "Usage: gitlooter [options] --url URL -o DIR\n\nDump a git repository from a website.\n\nOptions:\n")
		ap.parser.PrintDefaults()
	}

	ap.parser.StringVar(&ap.url, "url", "", "URL to dump (required)")
	ap.parser.StringVarP(&ap.directory, "out", "o", "", "Output directory (required)")

	ap.parser.StringVar(&ap.proxy, "proxy", "", "Proxy to use")
	ap.parser.StringVar(&ap.clientCertP12, "client-cert-p12", "", "Client certificate (PKCS#12)")
	ap.parser.StringVar(&ap.clientCertP12Password, "client-cert-p12-password", "", "Certificate password")

	ap.parser.Float64VarP(&ap.delay, "delay", "d", 0, "Delay between requests (seconds)")

	ap.parser.IntVarP(&ap.jobs, "jobs", "j", 10, "Simultaneous requests")
	ap.parser.IntVarP(&ap.retry, "retry", "r", 3, "Request attempts before giving up")
	ap.parser.IntVarP(&ap.timeout, "timeout", "t", 3, "Timeout in seconds")

	ap.parser.StringVarP(&ap.userAgent, "user-agent", "u",
		"Mozilla/5.0 (Windows NT 10.0; rv:78.0) Gecko/20100101 Firefox/78.0",
		"User-agent")

	ap.parser.StringArrayVarP(&ap.headers, "header", "H", nil,
		"Extra HTTP header, e.g. NAME=VALUE")

	ap.parser.StringArrayVarP(&ap.branches, "branch", "b", nil,
		"Extra branch to check (repeatable)")
	
	ap.parser.BoolVarP(&ap.args.OnlyCheck, "only-check", "C", false, 
		"Only check if .git dir is reachable. Disable dumping")

	ap.parser.StringVarP(&ap.filePath, "file", "f", "",
		"Domain list file")
}
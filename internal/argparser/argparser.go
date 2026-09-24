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
	"errors"
	"os"

	"github.com/spf13/pflag"
)


type ArgParser struct {
	args   *Arguments
	parser *pflag.FlagSet

	url                   string
	urlList               []string
	directory             string
	proxy                 string
	clientCertP12         string
	clientCertP12Password string
	delay                 float64
	jobs                  int
	retry                 int
	timeout               int
	userAgent             string
	headers               []string
	branches              []string
	filePath              string
}



func NewParser() *ArgParser {
	return &ArgParser{}
}



func (ap *ArgParser) GetArgs() (*Arguments, error) {
	if err := ap.parse(); err != nil {
		return nil, err
	}

	headers, err := ap.validHeaders()
	if err != nil {
		return nil, err
	}

	args := &Arguments{
		ClientCertP12Password : ap.clientCertP12Password,
		ClientCertP12         : ap.clientCertP12,
		Directory			  : ap.directory,
		Proxy                 : ap.proxy,
		URL			          : ap.url,
		Jobs			      : ap.jobs,
		Retry			      : ap.retry,
		Timeout			      : ap.timeout,
		HTTPHeaders           : headers,
		Branches			  : ap.branches,
		Delay			      : ap.delay,
		URLList               : ap.urlList,
	}

	return args, nil
}



func (ap *ArgParser) parse() error {
	ap.createArgs()

	if err := ap.parser.Parse(os.Args[1:]); err != nil {
		handleHelp(err)
		return err
	}

	if err := ap.validFilePath(); err != nil {
		return err
	}

	if err := ap.validURL(); err != nil {
		ap.parser.Usage()
		return err
	}

	if err := ap.validJobs(); err != nil {
		return err
	}

	if err := ap.validRetry(); err != nil {
		return err
	}

	if err := ap.validTimeout(); err != nil {
		return err
	}

	if err := ap.validProxy(); err != nil {
		return err
	}

	if err := ap.validCertificate(); err != nil {
		return err
	}

	if err := ap.validDelay(); err != nil {
		return err
	}

	if err := ap.createDir(); err != nil {
		return err
	}

	return nil
}



func handleHelp(err error) {
	if errors.Is(err, pflag.ErrHelp) {
		os.Exit(0)
	}
}
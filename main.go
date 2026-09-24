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

package main

import (
	"gitbleed/internal/argparser"
	"gitbleed/internal/display"
	"gitbleed/internal/extractor"
	"gitbleed/internal/scan"
)



func main() {
	args, err := argparser.NewParser().GetArgs()
	if err != nil {
		display.Fatal(err)
	}

	if args.OnlyCheck {
		scan.Scan(args)
		return
	}

	g := extractor.New(args)
	if err := g.Execute(); err != nil {
		display.Fatal(err)
	}
}
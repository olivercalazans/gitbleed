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

package gitx

import (
	"os"

	"github.com/go-git/go-git/v5/plumbing/format/index"
)



func ParseStagingArea(indexPath string, objs map[string]struct{}) {
	f, err := os.Open(indexPath)
	if err != nil {
		return
	}
	defer f.Close()

	idx := &index.Index{}
	if err := index.NewDecoder(f).Decode(idx); err != nil {
		return
	}

	for _, entry := range idx.Entries {
		objs[entry.Hash.String()] = struct{}{}
	}
}
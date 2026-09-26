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

package check

import "strings"



func EnsureProto(raw string) string {
	if strings.HasPrefix(raw, "http://") || strings.HasPrefix(raw, "https://") {
		return raw
	}
	
	return "https://" + raw
}



func EnsureSufixGit(raw string) string {
	raw = strings.TrimRight(raw, "/")

	switch {
	case strings.HasSuffix(raw, "/.git/HEAD"):
		return raw

	case strings.HasSuffix(raw, "/HEAD"):
		return strings.TrimSuffix(raw, "/HEAD") + "/.git/HEAD"

	case strings.HasSuffix(raw, "/.git"):
		return raw + "/HEAD"

	default:
		return raw + "/.git/HEAD"
	}
}
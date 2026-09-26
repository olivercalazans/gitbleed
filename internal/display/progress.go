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
	"sync"
)

type Progress struct {
	mut    sync.Mutex
	done   int
	total  int
}



func NewProgress(total int) *Progress {
	p := &Progress{total: total}
	p.draw()
	return p
}



func (p *Progress) Hit(line string) {
	p.mut.Lock()
	defer p.mut.Unlock()

	p.done++

	fmt.Print("\r\033[K")
	fmt.Printf("%s\n", line)
	p.draw()
}



func (p *Progress) Miss() {
	p.mut.Lock()
	defer p.mut.Unlock()

	p.done++
	p.draw()
}



func (p *Progress) draw() {
	fmt.Printf("\r[%d/%d] Scanning...", p.done, p.total)
}



func (p *Progress) Done() {
	p.mut.Lock()
	defer p.mut.Unlock()
	fmt.Println()
}
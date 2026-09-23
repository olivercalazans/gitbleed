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

package workers

import (
	"context"
	"fmt"
	"sync"

	"gitbleed/internal/display"
)

// TaskFunc processa uma tarefa e devolve novas tarefas descobertas.
type TaskFunc func(ctx context.Context, task string) ([]string, error)



type taskSet struct {
	seen  map[string]struct{}
	queue []string
}



func newTaskSet(capacity int) *taskSet {
	return &taskSet{
		seen:  make(map[string]struct{}),
		queue: make([]string, 0, capacity),
	}
}



func (s *taskSet) add(tasks ...string) {
	for _, t := range tasks {
		if _, ok := s.seen[t]; ok {
			continue
		}

		s.seen[t] = struct{}{}
		s.queue = append(s.queue, t)
	}
}



func (s *taskSet) len() int {
	return len(s.queue)
}



func (s *taskSet) pop() string {
	t := s.queue[0]
	s.queue = s.queue[1:]
	return t
}



func RunTasks(ctx context.Context, jobs int, initial []string, fn TaskFunc) {
	if jobs < 1 {
		jobs = 1
	}

	pending := make(chan string, jobs)
	results := make(chan []string, jobs)

	var wg sync.WaitGroup
	startWorkers(ctx, jobs, pending, results, fn, &wg)

	dispatch(ctx, pending, results, initial)
	close(pending)
	wg.Wait()
}



func startWorkers(
	ctx       context.Context,
	jobs      int,
	pending   <-chan string,
	results   chan<- []string,
	fn        TaskFunc,
	wg       *sync.WaitGroup,
) {
	for i := 0; i < jobs; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			runWorker(ctx, pending, results, fn)
		}()
	}
}



func runWorker(
	ctx      context.Context,
	pending  <-chan string,
	results  chan<- []string,
	fn       TaskFunc,
) {
	for task := range pending {
		results <- executeTask(ctx, task, fn)
	}
}



func executeTask(ctx context.Context, task string, fn TaskFunc) []string {
	children, err := fn(ctx, task)

	if err != nil {
		display.Warning(fmt.Sprintf("task %q raised: %v", task, err))
		return nil
	}

	return children
}



func dispatch(
	ctx     context.Context,
	pending  chan<- string,
	results  <-chan []string,
	initial  []string,
) {
	tasks := newTaskSet(len(initial))
	tasks.add(initial...)

	inflight := 0
	for tasks.len() > 0 || inflight > 0 {
		if feed(ctx, pending, results, tasks, &inflight) {
			return 
		}
	}
}



func feed(
	ctx        context.Context,
	pending    chan<- string,
	results    <-chan []string,
	tasks     *taskSet,
	inflight  *int,
) bool {
	var sendCh chan<- string
	var sendVal string
	if tasks.len() > 0 {
		sendCh = pending
		sendVal = tasks.queue[0]
	}

	select {
	case sendCh <- sendVal:
		tasks.pop()
		*inflight++

	case children := <-results:
		*inflight--
		tasks.add(children...)

	case <-ctx.Done():
		return true
	}

	return false
}
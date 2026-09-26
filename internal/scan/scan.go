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

package scan

import (
	"context"

	"gitbleed/internal/argparser"
	"gitbleed/internal/check"
	"gitbleed/internal/display"
	"gitbleed/internal/workers"

	"golang.org/x/sync/errgroup"
)



func Scan(args *argparser.Arguments) {
	client := workers.NewClient(args)

	progress := display.NewProgress(len(args.URLList))
	defer progress.Done()

	g, ctx := errgroup.WithContext(context.Background())
	g.SetLimit(args.Jobs)

	for _, url := range args.URLList {
		g.Go(func() error {
			url = check.EnsureProto(url)
			url = check.EnsureSufixGit(url)
			
			resp, err := client.Get(ctx, url, false)
			if err != nil {
				progress.Miss()
				return nil
			}
			defer resp.Body.Close()

			if line, ok := display.FormatOnly200(resp); ok {
				progress.Hit(line)
			} else {
				progress.Miss()
			}

			return nil
		})
	}

	g.Wait()
}
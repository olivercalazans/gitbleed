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
	"crypto/tls"
	"net"
	"net/http"
	"time"

	"gitbleed/internal/argparser"
)



type Client struct {
	http     *http.Client
	noRedir  *http.Client
	headers   http.Header
	delay     time.Duration
}



func NewClient(args *argparser.Arguments) *Client {
	transport := &http.Transport{
		DisableCompression: true,
		DialContext: (&net.Dialer{
			Timeout   : 30 * time.Second, // TCP connect
			KeepAlive : 30 * time.Second,
		}).DialContext,
		TLSHandshakeTimeout   : 10 * time.Second,
		ResponseHeaderTimeout : 30 * time.Second, // headers
		IdleConnTimeout       : 90 * time.Second,
		TLSClientConfig       : &tls.Config{InsecureSkipVerify: true},
	}

	timeout := time.Duration(args.Timeout) * time.Second

	h := make(http.Header, len(args.HTTPHeaders))
	for k, v := range args.HTTPHeaders {
		h.Set(k, v)
	}
	h.Del("Accept-Encoding")


	httpFollow := &http.Client{
		Transport : transport,
		Timeout   : timeout,
		// CheckRedirect nil
	}

	httpNoRedir := &http.Client{
		Transport : transport,
		Timeout   : timeout,
		CheckRedirect: func(req *http.Request, via []*http.Request) error {
			return http.ErrUseLastResponse
		},
	}

	return &Client{
		http    : httpFollow,
		noRedir : httpNoRedir,
		headers : h,
		delay   : time.Duration(args.Delay * float64(time.Second)),
	}
}



func (c *Client) Get(ctx context.Context, url string, followRedirects bool) (*http.Response, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)

	if err != nil {
		return nil, err
	}

	req.Header = c.headers.Clone()

	client := c.noRedir
	if followRedirects {
		client = c.http
	}

	resp, err := client.Do(req)

	if c.delay > 0 {
		time.Sleep(c.delay)
	}

	return resp, err
}
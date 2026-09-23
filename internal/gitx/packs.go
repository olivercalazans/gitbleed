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
	"bytes"
	"encoding/binary"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	osfs "github.com/go-git/go-billy/v5/osfs"
	"github.com/go-git/go-git/v5/plumbing"
	"github.com/go-git/go-git/v5/plumbing/cache"
	"github.com/go-git/go-git/v5/plumbing/object"
	"github.com/go-git/go-git/v5/storage/filesystem"
)



func ProcessPackFiles(gitDir string, packed, objs map[string]struct{}) {
	packDir := filepath.Join(gitDir, "objects", "pack")
	entries, err := os.ReadDir(packDir)

	if err != nil {
		return
	}

	storage := filesystem.NewStorage(osfs.New(gitDir), cache.NewObjectLRUDefault())

	for _, e := range entries {
		name := e.Name()
		if !strings.HasPrefix(name, "pack-") || !strings.HasSuffix(name, ".idx") {
			continue
		}

		idxPath     := filepath.Join(packDir, name)
		hashes, err := readPackIndexHashes(idxPath)

		if err != nil {
			continue
		}

		for _, h := range hashes {
			packed[h.String()] = struct{}{}

			refs, err := referencedFromPack(storage, h)
			if err != nil {
				continue
			}

			for _, r := range refs {
				objs[r.String()] = struct{}{}
			}
		}
	}
}



func referencedFromPack(storage *filesystem.Storage, h plumbing.Hash) ([]plumbing.Hash, error) {
	encoded, err := storage.EncodedObject(plumbing.AnyObject, h)
	if err != nil {
		return nil, err
	}

	decoded, err := object.DecodeObject(storage, encoded)
	if err != nil {
		return nil, err
	}

	return ReferencedSHA1(decoded)
}



func readPackIndexHashes(path string) ([]plumbing.Hash, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}

	if len(data) < 8 {
		return nil, errors.New("idx file too short")
	}

	if !bytes.Equal(data[:4], []byte{0xff, 't', 'O', 'c'}) {
		return nil, errors.New("unsupported idx format (only v2)")
	}

	if version := binary.BigEndian.Uint32(data[4:8]); version != 2 {
		return nil, fmt.Errorf("unsupported idx version: %d", version)
	}

	fanoutEnd := 8 + 256*4
	if len(data) < fanoutEnd {
		return nil, errors.New("idx truncated (fanout)")
	}

	count := binary.BigEndian.Uint32(data[fanoutEnd-4 : fanoutEnd])

	shaStart := fanoutEnd
	shaEnd   := shaStart + int(count)*20
	if len(data) < shaEnd {
		return nil, errors.New("idx truncated (hashes)")
	}

	hashes := make([]plumbing.Hash, count)
	for i := uint32(0); i < count; i++ {
		off := shaStart + int(i)*20
		copy(hashes[i][:], data[off:off+20])
	}

	return hashes, nil
}
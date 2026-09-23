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
	"fmt"
	"io"
	"os"

	"github.com/go-git/go-git/v5/plumbing"
	"github.com/go-git/go-git/v5/plumbing/format/objfile"
	"github.com/go-git/go-git/v5/plumbing/object"
)



func ReferencedSHA1(obj object.Object) ([]plumbing.Hash, error) {
	var refs []plumbing.Hash

	switch o := obj.(type) {
	case *object.Commit:
		refs = append(refs, o.TreeHash)
		refs = append(refs, o.ParentHashes...)

	case *object.Tree:
		for _, entry := range o.Entries {
			refs = append(refs, entry.Hash)
		}

	case *object.Blob:
	case *object.Tag:
	default:
		return nil, fmt.Errorf("unexpected object type: %T", obj)
	}

	return refs, nil
}



func ParseLooseObject(path string) (object.Object, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()

	r, err := objfile.NewReader(f)
	if err != nil {
		return nil, err
	}
	defer r.Close()

	typ, size, err := r.Header()
	if err != nil {
		return nil, err
	}

	mem := new(plumbing.MemoryObject)
	mem.SetType(typ)
	mem.SetSize(size)

	w, err := mem.Writer()
	if err != nil {
		return nil, err
	}

	if _, err := io.Copy(w, r); err != nil {
		return nil, err
	}

	if err := w.Close(); err != nil {
		return nil, err
	}

	var obj object.Object
	switch typ {
	case plumbing.CommitObject : obj = new(object.Commit)
	case plumbing.TreeObject   : obj = new(object.Tree)
	case plumbing.BlobObject   : obj = new(object.Blob)
	case plumbing.TagObject    : obj = new(object.Tag)
	default                    : return nil, fmt.Errorf("unknown object type: %s", typ)
	}

	if err := obj.Decode(mem); err != nil {
		return nil, err

	}
	return obj, nil
}
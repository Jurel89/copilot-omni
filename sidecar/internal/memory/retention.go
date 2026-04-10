package memory

import (
	"encoding/json"
	"time"
)

func PruneByAge(store *Store, maxAge time.Duration) (int, error) {
	if store == nil {
		return 0, &Error{Code: "nil_store"}
	}

	return store.DeleteByAge(maxAge)
}

func PruneByCount(store *Store, maxRecords int, scope string) (int, error) {
	if store == nil {
		return 0, &Error{Code: "nil_store"}
	}
	if maxRecords <= 0 {
		return 0, nil
	}

	currentCount, err := store.RecordCount(scope)
	if err != nil {
		return 0, err
	}

	if currentCount <= maxRecords {
		return 0, nil
	}

	toDelete := currentCount - maxRecords
	if toDelete <= 0 {
		return 0, nil
	}

	return store.DeleteOldest(toDelete, scope)
}

func WipeScope(store *Store, scope string) error {
	if store == nil {
		return &Error{Code: "nil_store"}
	}
	return store.DeleteByScope(scope)
}

func ExportRecords(store *Store, scope string) ([]byte, error) {
	if store == nil {
		return nil, &Error{Code: "nil_store"}
	}

	records, err := store.Export(scope)
	if err != nil {
		return nil, err
	}

	if len(records) == 0 {
		return []byte("[]"), nil
	}

	data, err := json.MarshalIndent(records, "", "  ")
	if err != nil {
		return nil, &Error{Code: "export_marshal_failed", Err: err}
	}

	return data, nil
}

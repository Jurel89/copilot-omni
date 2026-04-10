package run

import "time"

type JournalEntry struct {
	RunID     string    `json:"run_id"`
	Timestamp time.Time `json:"timestamp"`
	Action    string    `json:"action"`
	From      Status    `json:"from"`
	To        Status    `json:"to"`
	Message   string    `json:"message,omitempty"`
}

type Journal struct {
	entries []JournalEntry
}

func NewJournal() *Journal {
	return &Journal{entries: make([]JournalEntry, 0)}
}

func (j *Journal) Record(entry JournalEntry) {
	if j == nil {
		return
	}

	j.entries = append(j.entries, entry)
}

func (j *Journal) Entries() []JournalEntry {
	if j == nil {
		return nil
	}

	entries := make([]JournalEntry, len(j.entries))
	copy(entries, j.entries)

	return entries
}

func (j *Journal) Latest() JournalEntry {
	if j == nil || len(j.entries) == 0 {
		return JournalEntry{}
	}

	return j.entries[len(j.entries)-1]
}

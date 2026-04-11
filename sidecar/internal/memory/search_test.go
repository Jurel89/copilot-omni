package memory

import (
	"path/filepath"
	"strings"
	"testing"
	"time"
)

type searchFixture map[string]*MemoryRecord

func TestSearch(t *testing.T) {
	tests := []struct {
		name   string
		setup  func(t *testing.T, store *Store) searchFixture
		query  SearchQuery
		assert func(t *testing.T, result *SearchResult, fixture searchFixture)
	}{
		{
			name: "full text search scores title and content matches and extracts snippets",
			setup: func(t *testing.T, store *Store) searchFixture {
				t.Helper()

				createdAt := time.Now().UTC().Add(-1 * time.Hour)
				bestContent := strings.Repeat("lead ", 12) +
					"before apollo rollout and after context for snippet extraction " +
					strings.Repeat("tail ", 24)

				fixture := searchFixture{
					"title_only": mustCreateSearchRecord(t, store, searchRecord(createdAt, func(record *MemoryRecord) {
						record.Title = "apollo rollout title match"
						record.Content = "content without either query term"
					})),
					"content_only": mustCreateSearchRecord(t, store, searchRecord(createdAt, func(record *MemoryRecord) {
						record.Title = "generic record"
						record.Content = "short context before apollo rollout and after content"
					})),
					"best": mustCreateSearchRecord(t, store, searchRecord(createdAt, func(record *MemoryRecord) {
						record.Title = "apollo rollout apollo rollout"
						record.Content = bestContent
					})),
				}

				mustCreateSearchRecord(t, store, searchRecord(createdAt, func(record *MemoryRecord) {
					record.Title = "irrelevant"
					record.Content = "this record does not match the full text query"
				}))

				return fixture
			},
			query: SearchQuery{Query: "apollo rollout"},
			assert: func(t *testing.T, result *SearchResult, fixture searchFixture) {
				t.Helper()

				if result.Total != 3 {
					t.Fatalf("Search().Total = %d, want 3", result.Total)
				}
				if len(result.Records) != 3 {
					t.Fatalf("len(Search().Records) = %d, want 3", len(result.Records))
				}

				byID := scoredResultsByID(result)
				for name, record := range fixture {
					if _, ok := byID[record.ID]; !ok {
						t.Fatalf("missing %s record %q in search results", name, record.ID)
					}
				}

				for _, got := range result.Records {
					if got.MatchType != "fts" {
						t.Fatalf("Search() MatchType = %q, want %q", got.MatchType, "fts")
					}
					if got.Score <= 0 {
						t.Fatalf("Search() Score = %f, want > 0", got.Score)
					}
				}

				if result.Records[0].Record.ID != fixture["best"].ID {
					t.Fatalf("top result ID = %q, want %q", result.Records[0].Record.ID, fixture["best"].ID)
				}

				bestScore := byID[fixture["best"].ID].Score
				titleOnlyScore := byID[fixture["title_only"].ID].Score
				contentOnlyScore := byID[fixture["content_only"].ID].Score
				if bestScore <= titleOnlyScore {
					t.Fatalf("best score = %f, want greater than title-only score %f", bestScore, titleOnlyScore)
				}
				if titleOnlyScore <= contentOnlyScore {
					t.Fatalf("title-only score = %f, want greater than content-only score %f", titleOnlyScore, contentOnlyScore)
				}

				snippet := byID[fixture["best"].ID].Snippet
				if !strings.HasPrefix(snippet, "...") {
					t.Fatalf("snippet = %q, want leading ellipsis", snippet)
				}
				if !strings.HasSuffix(snippet, "...") {
					t.Fatalf("snippet = %q, want trailing ellipsis", snippet)
				}
				if !strings.Contains(snippet, "before apollo rollout and after context for snippet extraction") {
					t.Fatalf("snippet = %q, want matched context", snippet)
				}
			},
		},
		{
			name: "metadata only search filters by type scope run id tags and trust level",
			setup: func(t *testing.T, store *Store) searchFixture {
				t.Helper()

				createdAt := time.Now().UTC().Add(-2 * time.Hour)
				fixture := searchFixture{
					"match": mustCreateSearchRecord(t, store, searchRecord(createdAt, func(record *MemoryRecord) {
						record.Type = TypeDecision
						record.Scope = ScopeGlobal
						record.RunID = "run-meta"
						record.Tags = []string{"ops", "release"}
						record.TrustLevel = TrustHigh
						record.Title = "global decision"
						record.Content = "metadata-only target"
					})),
				}

				mustCreateSearchRecord(t, store, searchRecord(createdAt, func(record *MemoryRecord) {
					record.Type = TypePlan
					record.Scope = ScopeGlobal
					record.RunID = "run-meta"
					record.Tags = []string{"ops", "release"}
					record.TrustLevel = TrustHigh
				}))
				mustCreateSearchRecord(t, store, searchRecord(createdAt, func(record *MemoryRecord) {
					record.Type = TypeDecision
					record.Scope = ScopeProject
					record.RunID = "run-meta"
					record.Tags = []string{"ops", "release"}
					record.TrustLevel = TrustHigh
				}))
				mustCreateSearchRecord(t, store, searchRecord(createdAt, func(record *MemoryRecord) {
					record.Type = TypeDecision
					record.Scope = ScopeGlobal
					record.RunID = "run-other"
					record.Tags = []string{"ops", "release"}
					record.TrustLevel = TrustHigh
				}))
				mustCreateSearchRecord(t, store, searchRecord(createdAt, func(record *MemoryRecord) {
					record.Type = TypeDecision
					record.Scope = ScopeGlobal
					record.RunID = "run-meta"
					record.Tags = []string{"audit"}
					record.TrustLevel = TrustHigh
				}))
				mustCreateSearchRecord(t, store, searchRecord(createdAt, func(record *MemoryRecord) {
					record.Type = TypeDecision
					record.Scope = ScopeGlobal
					record.RunID = "run-meta"
					record.Tags = []string{"ops", "release"}
					record.TrustLevel = TrustMedium
				}))

				return fixture
			},
			query: SearchQuery{
				Type:       TypeDecision,
				Scope:      ScopeGlobal,
				RunID:      "run-meta",
				Tags:       []string{"ops"},
				TrustLevel: TrustHigh,
			},
			assert: func(t *testing.T, result *SearchResult, fixture searchFixture) {
				t.Helper()

				if result.Total != 1 {
					t.Fatalf("Search().Total = %d, want 1", result.Total)
				}
				if len(result.Records) != 1 {
					t.Fatalf("len(Search().Records) = %d, want 1", len(result.Records))
				}

				got := result.Records[0]
				if got.Record.ID != fixture["match"].ID {
					t.Fatalf("Search() record ID = %q, want %q", got.Record.ID, fixture["match"].ID)
				}
				if got.MatchType != "metadata" {
					t.Fatalf("Search() MatchType = %q, want %q", got.MatchType, "metadata")
				}
				if got.Snippet != "" {
					t.Fatalf("Search() Snippet = %q, want empty string", got.Snippet)
				}
				if got.Score <= 0 || got.Score > 1 {
					t.Fatalf("Search() Score = %f, want 0 < score <= 1", got.Score)
				}
			},
		},
		{
			name: "combined full text and metadata filters narrow to matching records",
			setup: func(t *testing.T, store *Store) searchFixture {
				t.Helper()

				createdAt := time.Now().UTC().Add(-90 * time.Minute)
				fixture := searchFixture{
					"match": mustCreateSearchRecord(t, store, searchRecord(createdAt, func(record *MemoryRecord) {
						record.Type = TypeDecision
						record.Scope = ScopeGlobal
						record.RunID = "run-combined"
						record.Tags = []string{"ops", "release"}
						record.TrustLevel = TrustHigh
						record.Title = "policy review decision"
						record.Content = strings.Repeat("preface ", 10) +
							"policy review guides rollout safely" +
							strings.Repeat(" suffix", 12)
					})),
				}

				mustCreateSearchRecord(t, store, searchRecord(createdAt, func(record *MemoryRecord) {
					record.Type = TypeDecision
					record.Scope = ScopeProject
					record.RunID = "run-combined"
					record.Tags = []string{"ops", "release"}
					record.TrustLevel = TrustHigh
					record.Title = "policy review project"
					record.Content = "policy review guides rollout safely"
				}))
				mustCreateSearchRecord(t, store, searchRecord(createdAt, func(record *MemoryRecord) {
					record.Type = TypeDecision
					record.Scope = ScopeGlobal
					record.RunID = "run-combined"
					record.Tags = []string{"ops", "release"}
					record.TrustLevel = TrustHigh
					record.Title = "release checklist"
					record.Content = "this entry does not include the query phrase"
				}))
				mustCreateSearchRecord(t, store, searchRecord(createdAt, func(record *MemoryRecord) {
					record.Type = TypeDecision
					record.Scope = ScopeGlobal
					record.RunID = "run-combined"
					record.Tags = []string{"audit"}
					record.TrustLevel = TrustHigh
					record.Title = "policy review audit"
					record.Content = "policy review guides rollout safely"
				}))

				return fixture
			},
			query: SearchQuery{
				Query:      "policy review",
				Type:       TypeDecision,
				Scope:      ScopeGlobal,
				RunID:      "run-combined",
				Tags:       []string{"ops"},
				TrustLevel: TrustHigh,
			},
			assert: func(t *testing.T, result *SearchResult, fixture searchFixture) {
				t.Helper()

				if result.Total != 1 {
					t.Fatalf("Search().Total = %d, want 1", result.Total)
				}
				if len(result.Records) != 1 {
					t.Fatalf("len(Search().Records) = %d, want 1", len(result.Records))
				}

				got := result.Records[0]
				if got.Record.ID != fixture["match"].ID {
					t.Fatalf("Search() record ID = %q, want %q", got.Record.ID, fixture["match"].ID)
				}
				if got.MatchType != "fts" {
					t.Fatalf("Search() MatchType = %q, want %q", got.MatchType, "fts")
				}
				if got.Score <= 0 {
					t.Fatalf("Search() Score = %f, want > 0", got.Score)
				}
				if !strings.Contains(got.Snippet, "policy review guides rollout safely") {
					t.Fatalf("Search() Snippet = %q, want matched context", got.Snippet)
				}
			},
		},
		{
			name: "metadata search applies offset and limit after scoring",
			setup: func(t *testing.T, store *Store) searchFixture {
				t.Helper()

				now := time.Now().UTC()
				fixture := searchFixture{
					"oldest": mustCreateSearchRecord(t, store, searchRecord(now.Add(-4*time.Hour), func(record *MemoryRecord) {
						record.Title = "oldest"
					})),
					"older": mustCreateSearchRecord(t, store, searchRecord(now.Add(-3*time.Hour), func(record *MemoryRecord) {
						record.Title = "older"
					})),
					"newer": mustCreateSearchRecord(t, store, searchRecord(now.Add(-2*time.Hour), func(record *MemoryRecord) {
						record.Title = "newer"
					})),
					"newest": mustCreateSearchRecord(t, store, searchRecord(now.Add(-1*time.Hour), func(record *MemoryRecord) {
						record.Title = "newest"
					})),
				}

				mustCreateSearchRecord(t, store, searchRecord(now.Add(-30*time.Minute), func(record *MemoryRecord) {
					record.Scope = ScopeGlobal
					record.Title = "filtered out by scope"
				}))

				return fixture
			},
			query: SearchQuery{Scope: ScopeProject, Limit: 2, Offset: 1},
			assert: func(t *testing.T, result *SearchResult, fixture searchFixture) {
				t.Helper()

				if result.Total != 4 {
					t.Fatalf("Search().Total = %d, want 4", result.Total)
				}
				if len(result.Records) != 2 {
					t.Fatalf("len(Search().Records) = %d, want 2", len(result.Records))
				}

				assertSearchResultIDs(t, result.Records, []string{fixture["newer"].ID, fixture["older"].ID})
				for _, got := range result.Records {
					if got.MatchType != "metadata" {
						t.Fatalf("Search() MatchType = %q, want %q", got.MatchType, "metadata")
					}
				}
				if result.Records[0].Score < result.Records[1].Score {
					t.Fatalf("scores are not sorted descending: %f < %f", result.Records[0].Score, result.Records[1].Score)
				}
			},
		},
		{
			name: "returns empty results when no records match",
			setup: func(t *testing.T, store *Store) searchFixture {
				t.Helper()
				mustCreateSearchRecord(t, store, searchRecord(time.Now().UTC().Add(-1*time.Hour), func(record *MemoryRecord) {
					record.Title = "existing record"
					record.Content = "this content never matches the requested query"
				}))
				return nil
			},
			query: SearchQuery{Query: "absent keyword"},
			assert: func(t *testing.T, result *SearchResult, _ searchFixture) {
				t.Helper()

				if result.Total != 0 {
					t.Fatalf("Search().Total = %d, want 0", result.Total)
				}
				if len(result.Records) != 0 {
					t.Fatalf("len(Search().Records) = %d, want 0", len(result.Records))
				}
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			store := newSearchTestStore(t)
			fixture := tt.setup(t, store)

			result, err := store.Search(tt.query)
			if err != nil {
				t.Fatalf("Search() error = %v", err)
			}
			if result == nil {
				t.Fatal("Search() result = nil, want non-nil result")
			}

			tt.assert(t, result, fixture)
		})
	}
}

func TestSearchLimitNormalization(t *testing.T) {
	tests := []struct {
		name         string
		limit        int
		recordCount  int
		wantLimit    int
		wantReturned int
	}{
		{
			name:         "clamps limit to maxSearchLimit",
			limit:        maxSearchLimit + 25,
			recordCount:  maxSearchLimit + 5,
			wantLimit:    maxSearchLimit,
			wantReturned: maxSearchLimit,
		},
		{
			name:         "uses default limit when limit is zero",
			limit:        0,
			recordCount:  defaultSearchLimit + 2,
			wantLimit:    defaultSearchLimit,
			wantReturned: defaultSearchLimit,
		},
		{
			name:         "uses default limit when limit is negative",
			limit:        -3,
			recordCount:  defaultSearchLimit + 2,
			wantLimit:    defaultSearchLimit,
			wantReturned: defaultSearchLimit,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			store := newSearchTestStore(t)
			seedMetadataSearchRecords(t, store, tt.recordCount)

			result, err := store.Search(SearchQuery{Limit: tt.limit})
			if err != nil {
				t.Fatalf("Search() error = %v", err)
			}
			if result == nil {
				t.Fatal("Search() result = nil, want non-nil result")
			}

			if result.Query.Limit != tt.wantLimit {
				t.Fatalf("Search().Query.Limit = %d, want %d", result.Query.Limit, tt.wantLimit)
			}
			if result.Total != tt.recordCount {
				t.Fatalf("Search().Total = %d, want %d", result.Total, tt.recordCount)
			}
			if len(result.Records) != tt.wantReturned {
				t.Fatalf("len(Search().Records) = %d, want %d", len(result.Records), tt.wantReturned)
			}
			for _, got := range result.Records {
				if got.MatchType != "metadata" {
					t.Fatalf("Search() MatchType = %q, want %q", got.MatchType, "metadata")
				}
			}
		})
	}
}

func TestSearchNilStore(t *testing.T) {
	var store *Store

	result, err := store.Search(SearchQuery{Query: "apollo"})
	if result != nil {
		t.Fatalf("Search() result = %#v, want nil", result)
	}
	requireMemoryErrorCode(t, err, "nil_store")
}

func newSearchTestStore(t *testing.T) *Store {
	t.Helper()

	dbPath := filepath.Join(t.TempDir(), "memory.db")
	store, err := NewStore(dbPath)
	if err != nil {
		t.Fatalf("NewStore(%q) error = %v", dbPath, err)
	}

	t.Cleanup(func() {
		if closeErr := store.Close(); closeErr != nil {
			t.Errorf("Close() error = %v", closeErr)
		}
	})

	return store
}

func mustCreateSearchRecord(t *testing.T, store *Store, record *MemoryRecord) *MemoryRecord {
	t.Helper()

	if err := store.Create(record); err != nil {
		t.Fatalf("Create() error = %v", err)
	}

	return record
}

func searchRecord(createdAt time.Time, mutate func(*MemoryRecord)) *MemoryRecord {
	record := &MemoryRecord{
		Type:        TypeNote,
		Source:      SourceUser,
		Scope:       ScopeProject,
		Title:       "search test title",
		Content:     "search test content",
		TrustLevel:  TrustMedium,
		Sensitivity: SensitivityNormal,
		CreatedAt:   createdAt,
	}

	if mutate != nil {
		mutate(record)
	}

	return record
}

func scoredResultsByID(result *SearchResult) map[string]ScoredRecord {
	byID := make(map[string]ScoredRecord, len(result.Records))
	for _, record := range result.Records {
		byID[record.Record.ID] = record
	}
	return byID
}

func assertSearchResultIDs(t *testing.T, records []ScoredRecord, want []string) {
	t.Helper()

	if len(records) != len(want) {
		t.Fatalf("len(records) = %d, want %d", len(records), len(want))
	}

	for i := range want {
		if records[i].Record.ID != want[i] {
			t.Fatalf("records[%d].Record.ID = %q, want %q", i, records[i].Record.ID, want[i])
		}
	}
}

func seedMetadataSearchRecords(t *testing.T, store *Store, count int) {
	t.Helper()

	base := time.Now().UTC().Add(-time.Duration(count) * time.Minute)
	for i := range count {
		record := searchRecord(base.Add(time.Duration(i)*time.Minute), func(record *MemoryRecord) {
			record.Title = "metadata record"
			record.Content = "metadata-only search record"
		})
		mustCreateSearchRecord(t, store, record)
	}
}

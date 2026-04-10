package memory

import (
	"fmt"
	"math"
	"sort"
	"strings"
	"time"
)

type SearchQuery struct {
	Query      string   `json:"query"`
	Type       string   `json:"type,omitempty"`
	Scope      string   `json:"scope,omitempty"`
	RunID      string   `json:"run_id,omitempty"`
	Tags       []string `json:"tags,omitempty"`
	TrustLevel string   `json:"trust_level,omitempty"`
	Limit      int      `json:"limit,omitempty"`
	Offset     int      `json:"offset,omitempty"`
}

type ScoredRecord struct {
	Record    MemoryRecord `json:"record"`
	Score     float64      `json:"score"`
	Snippet   string       `json:"snippet,omitempty"`
	MatchType string       `json:"match_type"`
}

type SearchResult struct {
	Records []ScoredRecord `json:"records"`
	Total   int            `json:"total"`
	Query   SearchQuery    `json:"query"`
}

const (
	defaultSearchLimit = 10
	maxSearchLimit     = 100
	recencyHalfLife    = 7 * 24 * time.Hour
)

func (s *Store) Search(query SearchQuery) (*SearchResult, error) {
	if s == nil {
		return nil, &Error{Code: "nil_store"}
	}

	if query.Limit <= 0 {
		query.Limit = defaultSearchLimit
	}
	if query.Limit > maxSearchLimit {
		query.Limit = maxSearchLimit
	}

	trimmedQuery := strings.TrimSpace(query.Query)
	if trimmedQuery == "" {
		return s.searchByMetadata(query)
	}
	return s.searchFullText(trimmedQuery, query)
}

func (s *Store) searchFullText(ftsQuery string, query SearchQuery) (*SearchResult, error) {
	terms := strings.Fields(ftsQuery)
	conditions := make([]string, 0, len(terms))
	args := make([]interface{}, 0, len(terms)*2)
	for _, term := range terms {
		likeTerm := "%" + term + "%"
		conditions = append(conditions, "(title LIKE ? OR content LIKE ?)")
		args = append(args, likeTerm, likeTerm)
	}
	appendFilterConditions(&conditions, &args, query)

	whereClause := "WHERE " + strings.Join(conditions, " AND ")

	countQuery := fmt.Sprintf(`SELECT COUNT(*) FROM memory_records %s`, whereClause)
	var total int
	if err := s.db.QueryRow(countQuery, args...).Scan(&total); err != nil {
		return nil, &Error{Code: "search_count_failed", Err: err}
	}

	dataArgs := make([]interface{}, len(args))
	copy(dataArgs, args)

	dataQuery := fmt.Sprintf(`
		SELECT id, type, source, scope, run_id, title, content, metadata, tags,
		       trust_level, sensitivity, created_at, updated_at
		FROM memory_records %s
	`, whereClause)

	rows, err := s.db.Query(dataQuery, dataArgs...)
	if err != nil {
		return nil, &Error{Code: "search_query_failed", Err: err}
	}
	defer rows.Close()

	records, err := scanRecords(rows)
	if err != nil {
		return nil, err
	}

	now := time.Now().UTC()
	scored := make([]ScoredRecord, 0, len(records))
	for _, r := range records {
		score := computeFTSScore(r, ftsQuery, now)
		snippet := extractSnippet(r.Content, ftsQuery)
		scored = append(scored, ScoredRecord{
			Record:    r,
			Score:     score,
			Snippet:   snippet,
			MatchType: "fts",
		})
	}
	sort.Slice(scored, func(i, j int) bool { return scored[i].Score > scored[j].Score })

	// Apply offset/limit after scoring and sorting
	start := query.Offset
	if start > len(scored) {
		start = len(scored)
	}
	end := len(scored)
	if query.Limit > 0 && start+query.Limit < end {
		end = start + query.Limit
	}
	scored = scored[start:end]

	return &SearchResult{
		Records: scored,
		Total:   total,
		Query:   query,
	}, nil
}

func (s *Store) searchByMetadata(query SearchQuery) (*SearchResult, error) {
	conditions := []string{}
	args := []interface{}{}
	appendFilterConditions(&conditions, &args, query)

	whereClause := "WHERE 1=1"
	if len(conditions) > 0 {
		whereClause = "WHERE " + strings.Join(conditions, " AND ")
	}

	countQuery := fmt.Sprintf(`SELECT COUNT(*) FROM memory_records %s`, whereClause)
	var total int
	if err := s.db.QueryRow(countQuery, args...).Scan(&total); err != nil {
		return nil, &Error{Code: "search_count_failed", Err: err}
	}

	dataArgs := make([]interface{}, len(args))
	copy(dataArgs, args)

	dataQuery := fmt.Sprintf(`
		SELECT id, type, source, scope, run_id, title, content, metadata, tags,
		       trust_level, sensitivity, created_at, updated_at
		FROM memory_records %s
	`, whereClause)

	rows, err := s.db.Query(dataQuery, dataArgs...)
	if err != nil {
		return nil, &Error{Code: "search_query_failed", Err: err}
	}
	defer rows.Close()

	records, err := scanRecords(rows)
	if err != nil {
		return nil, err
	}

	now := time.Now().UTC()
	scored := make([]ScoredRecord, 0, len(records))
	for _, r := range records {
		score := computeRecencyScore(r.CreatedAt, now)
		scored = append(scored, ScoredRecord{
			Record:    r,
			Score:     score,
			MatchType: "metadata",
		})
	}
	sort.Slice(scored, func(i, j int) bool { return scored[i].Score > scored[j].Score })

	// Apply offset/limit after scoring and sorting
	start := query.Offset
	if start > len(scored) {
		start = len(scored)
	}
	end := len(scored)
	if query.Limit > 0 && start+query.Limit < end {
		end = start + query.Limit
	}
	scored = scored[start:end]

	return &SearchResult{
		Records: scored,
		Total:   total,
		Query:   query,
	}, nil
}

func appendFilterConditions(conditions *[]string, args *[]interface{}, query SearchQuery) {
	if query.Type != "" {
		*conditions = append(*conditions, "type = ?")
		*args = append(*args, query.Type)
	}
	if query.Scope != "" {
		*conditions = append(*conditions, "scope = ?")
		*args = append(*args, query.Scope)
	}
	if query.RunID != "" {
		*conditions = append(*conditions, "run_id = ?")
		*args = append(*args, query.RunID)
	}
	if query.TrustLevel != "" {
		*conditions = append(*conditions, "trust_level = ?")
		*args = append(*args, query.TrustLevel)
	}
	if len(query.Tags) > 0 {
		orParts := make([]string, 0, len(query.Tags))
		for _, tag := range query.Tags {
			orParts = append(orParts, "(tags LIKE ?)")
			*args = append(*args, "%,"+tag+",%")
		}
		*conditions = append(*conditions, "("+strings.Join(orParts, " OR ")+")")
	}
}

func computeFTSScore(record MemoryRecord, query string, now time.Time) float64 {
	baseScore := 1.0

	lowerContent := strings.ToLower(record.Content)
	lowerTitle := strings.ToLower(record.Title)
	lowerQuery := strings.ToLower(query)

	queryTerms := strings.Fields(lowerQuery)
	for _, term := range queryTerms {
		titleCount := strings.Count(lowerTitle, term)
		contentCount := strings.Count(lowerContent, term)
		baseScore += float64(titleCount) * 2.0
		baseScore += float64(contentCount) * 0.5
	}

	return baseScore + computeRecencyScore(record.CreatedAt, now)
}

func computeRecencyScore(createdAt, now time.Time) float64 {
	age := now.Sub(createdAt)
	if age < 0 {
		age = 0
	}
	halfLives := float64(age) / float64(recencyHalfLife)
	return math.Pow(0.5, halfLives)
}

func extractSnippet(content, query string) string {
	lowerContent := strings.ToLower(content)
	lowerQuery := strings.ToLower(query)

	idx := strings.Index(lowerContent, lowerQuery)
	if idx < 0 {
		for _, term := range strings.Fields(lowerQuery) {
			idx = strings.Index(lowerContent, term)
			if idx >= 0 {
				break
			}
		}
	}

	if idx < 0 {
		if len(content) > 200 {
			return content[:200] + "..."
		}
		return content
	}

	start := idx - 50
	if start < 0 {
		start = 0
	}
	end := idx + len(query) + 100
	if end > len(content) {
		end = len(content)
	}

	snippet := content[start:end]
	if start > 0 {
		snippet = "..." + snippet
	}
	if end < len(content) {
		snippet = snippet + "..."
	}

	if len(snippet) > 300 {
		snippet = snippet[:300] + "..."
	}

	return snippet
}

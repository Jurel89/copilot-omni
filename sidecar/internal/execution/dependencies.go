package execution

import (
	"fmt"
	"sort"
	"strings"
)

func BuildDependencyGraph(tasks []TaskInfo) (map[string][]string, error) {
	graph := make(map[string][]string, len(tasks))
	knownTaskIDs := make(map[string]struct{}, len(tasks))

	for _, task := range tasks {
		if strings.TrimSpace(task.ID) == "" {
			return nil, &Error{Code: reasonCodeInvalidTask, Err: fmt.Errorf("task id must not be empty")}
		}
		if _, exists := knownTaskIDs[task.ID]; exists {
			return nil, &Error{Code: reasonCodeDuplicateTaskID, TaskID: task.ID}
		}
		knownTaskIDs[task.ID] = struct{}{}
		graph[task.ID] = cloneTrimmedStrings(task.Dependencies)
	}

	for taskID, dependencies := range graph {
		seenDependencies := make(map[string]struct{}, len(dependencies))
		for _, dependencyID := range dependencies {
			if dependencyID == "" {
				return nil, &Error{Code: reasonCodeUnknownTaskRef, TaskID: taskID, DependencyID: dependencyID}
			}
			if _, ok := knownTaskIDs[dependencyID]; !ok {
				return nil, &Error{Code: reasonCodeUnknownTaskRef, TaskID: taskID, DependencyID: dependencyID}
			}
			if _, exists := seenDependencies[dependencyID]; exists {
				continue
			}
			seenDependencies[dependencyID] = struct{}{}
		}
	}

	return graph, nil
}

func DetectCycle(graph map[string][]string) ([]string, error) {
	if graph == nil {
		return nil, nil
	}

	const (
		unvisited = iota
		visiting
		visited
	)

	state := make(map[string]int, len(graph))
	stack := make([]string, 0, len(graph))
	sortedNodes := sortedKeys(graph)

	var visit func(string) ([]string, error)
	visit = func(node string) ([]string, error) {
		state[node] = visiting
		stack = append(stack, node)

		dependencies := append([]string(nil), graph[node]...)
		sort.Strings(dependencies)
		for _, dependencyID := range dependencies {
			if _, ok := graph[dependencyID]; !ok {
				return nil, &Error{Code: reasonCodeUnknownTaskRef, TaskID: node, DependencyID: dependencyID}
			}

			switch state[dependencyID] {
			case unvisited:
				cycle, err := visit(dependencyID)
				if err != nil {
					return nil, err
				}
				if len(cycle) > 0 {
					return cycle, nil
				}
			case visiting:
				return buildCyclePath(stack, dependencyID), nil
			}
		}

		stack = stack[:len(stack)-1]
		state[node] = visited
		return nil, nil
	}

	for _, node := range sortedNodes {
		if state[node] != unvisited {
			continue
		}
		cycle, err := visit(node)
		if err != nil {
			return nil, err
		}
		if len(cycle) > 0 {
			return cycle, nil
		}
	}

	return nil, nil
}

func TopologicalSort(graph map[string][]string) ([]string, error) {
	if graph == nil {
		return nil, nil
	}

	indegree := make(map[string]int, len(graph))
	dependents := make(map[string][]string, len(graph))

	for taskID := range graph {
		indegree[taskID] = 0
	}

	for taskID, dependencies := range graph {
		uniqueDependencies := make(map[string]struct{}, len(dependencies))
		for _, dependencyID := range dependencies {
			if _, ok := graph[dependencyID]; !ok {
				return nil, &Error{Code: reasonCodeUnknownTaskRef, TaskID: taskID, DependencyID: dependencyID}
			}
			if _, exists := uniqueDependencies[dependencyID]; exists {
				continue
			}
			uniqueDependencies[dependencyID] = struct{}{}
			indegree[taskID]++
			dependents[dependencyID] = append(dependents[dependencyID], taskID)
		}
	}

	queue := make([]string, 0)
	for taskID, degree := range indegree {
		if degree == 0 {
			queue = append(queue, taskID)
		}
	}
	sort.Strings(queue)

	ordered := make([]string, 0, len(graph))
	for len(queue) > 0 {
		node := queue[0]
		queue = queue[1:]
		ordered = append(ordered, node)

		nextDependents := append([]string(nil), dependents[node]...)
		sort.Strings(nextDependents)
		for _, dependentID := range nextDependents {
			indegree[dependentID]--
			if indegree[dependentID] == 0 {
				queue = append(queue, dependentID)
				sort.Strings(queue)
			}
		}
	}

	if len(ordered) != len(graph) {
		cycle, err := DetectCycle(graph)
		if err != nil {
			return nil, err
		}
		if len(cycle) > 0 {
			return nil, &Error{Code: reasonCodeCyclicDependency, TaskID: strings.Join(cycle, " -> ")}
		}
		return nil, &Error{Code: reasonCodeTopologicalSort, Err: fmt.Errorf("dependency graph contains unreachable tasks")}
	}

	return ordered, nil
}

func buildCyclePath(stack []string, start string) []string {
	startIndex := -1
	for index, node := range stack {
		if node == start {
			startIndex = index
			break
		}
	}
	if startIndex < 0 {
		return []string{start}
	}

	cycle := append([]string(nil), stack[startIndex:]...)
	cycle = append(cycle, start)
	return cycle
}

func sortedKeys(graph map[string][]string) []string {
	keys := make([]string, 0, len(graph))
	for key := range graph {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	return keys
}

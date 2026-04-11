package support

import (
	"os"
	"runtime"
)

type Collector struct{}

func NewCollector() *Collector {
	return &Collector{}
}

func (c *Collector) CollectSystemInfo() (SystemInfo, error) {
	hostname, _ := os.Hostname()
	wd, _ := os.Getwd()

	return SystemInfo{
		OS:           runtime.GOOS,
		Architecture: runtime.GOARCH,
		GoVersion:    runtime.Version(),
		Hostname:     hostname,
		WorkingDir:   wd,
		Environment:  map[string]string{},
	}, nil
}

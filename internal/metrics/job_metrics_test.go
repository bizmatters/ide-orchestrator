package metrics

import (
	"context"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestJobMetrics_Creation(t *testing.T) {
	t.Run("successfully create job metrics", func(t *testing.T) {
		metrics, err := NewJobMetrics()
		require.NoError(t, err)
		assert.NotNil(t, metrics)
		assert.NotNil(t, metrics.jobsCreatedCounter)
		assert.NotNil(t, metrics.jobsCompletedCounter)
		assert.NotNil(t, metrics.jobsFailedCounter)
		assert.NotNil(t, metrics.jobDurationHistogram)
		assert.NotNil(t, metrics.jobsActiveGauge)
	})
}

func TestJobMetrics_RecordJobCreated(t *testing.T) {
	metrics, err := NewJobMetrics()
	require.NoError(t, err)

	t.Run("record job creation", func(t *testing.T) {
		ctx := context.Background()
		agentID := "test-agent-123"
		webhookID := "test-webhook-456"

		// Should not panic
		assert.NotPanics(t, func() {
			metrics.RecordJobCreated(ctx, agentID, webhookID)
		})
	})

	t.Run("record multiple job creations", func(t *testing.T) {
		ctx := context.Background()

		for i := 0; i < 5; i++ {
			agentID := "agent-" + string(rune(i))
			webhookID := "webhook-" + string(rune(i))
			metrics.RecordJobCreated(ctx, agentID, webhookID)
		}
	})
}

func TestJobMetrics_RecordJobCompleted(t *testing.T) {
	metrics, err := NewJobMetrics()
	require.NoError(t, err)

	t.Run("record job completion with duration", func(t *testing.T) {
		ctx := context.Background()
		agentID := "test-agent-123"
		webhookID := "test-webhook-456"
		duration := 5 * time.Second

		assert.NotPanics(t, func() {
			metrics.RecordJobCompleted(ctx, agentID, webhookID, duration)
		})
	})

	t.Run("record completion with various durations", func(t *testing.T) {
		ctx := context.Background()
		durations := []time.Duration{
			100 * time.Millisecond,
			1 * time.Second,
			10 * time.Second,
			1 * time.Minute,
		}

		for i, duration := range durations {
			agentID := "agent-" + string(rune(i))
			webhookID := "webhook-" + string(rune(i))
			metrics.RecordJobCompleted(ctx, agentID, webhookID, duration)
		}
	})
}

func TestJobMetrics_RecordJobFailed(t *testing.T) {
	metrics, err := NewJobMetrics()
	require.NoError(t, err)

	t.Run("record job failure with error type", func(t *testing.T) {
		ctx := context.Background()
		agentID := "test-agent-123"
		webhookID := "test-webhook-456"
		errorType := "execution_error"
		duration := 3 * time.Second

		assert.NotPanics(t, func() {
			metrics.RecordJobFailed(ctx, agentID, webhookID, errorType, duration)
		})
	})

	t.Run("record failures with different error types", func(t *testing.T) {
		ctx := context.Background()
		errorTypes := []string{
			"execution_error",
			"timeout_error",
			"validation_error",
			"system_error",
		}

		for i, errorType := range errorTypes {
			agentID := "agent-" + string(rune(i))
			webhookID := "webhook-" + string(rune(i))
			duration := time.Duration(i+1) * time.Second
			metrics.RecordJobFailed(ctx, agentID, webhookID, errorType, duration)
		}
	})
}

func TestJobMetrics_ActiveJobsGauge(t *testing.T) {
	metrics, err := NewJobMetrics()
	require.NoError(t, err)

	t.Run("active jobs counter increments and decrements", func(t *testing.T) {
		ctx := context.Background()
		agentID := "test-agent-123"
		webhookID := "test-webhook-456"

		// Create job (increments active gauge)
		metrics.RecordJobCreated(ctx, agentID, webhookID)

		// Complete job (decrements active gauge)
		duration := 2 * time.Second
		metrics.RecordJobCompleted(ctx, agentID, webhookID, duration)
	})

	t.Run("active jobs with failures", func(t *testing.T) {
		ctx := context.Background()
		agentID := "test-agent-456"
		webhookID := "test-webhook-789"

		// Create job
		metrics.RecordJobCreated(ctx, agentID, webhookID)

		// Fail job (decrements active gauge)
		duration := 1 * time.Second
		metrics.RecordJobFailed(ctx, agentID, webhookID, "error", duration)
	})
}

func TestJobMetrics_ConcurrentRecording(t *testing.T) {
	metrics, err := NewJobMetrics()
	require.NoError(t, err)

	t.Run("handle concurrent metric recording", func(t *testing.T) {
		ctx := context.Background()
		done := make(chan bool)

		// Simulate concurrent job creation
		for i := 0; i < 10; i++ {
			go func(id int) {
				agentID := "concurrent-agent-" + string(rune(id))
				webhookID := "concurrent-webhook-" + string(rune(id))

				metrics.RecordJobCreated(ctx, agentID, webhookID)

				// Randomly complete or fail
				duration := time.Duration(id) * 100 * time.Millisecond
				if id%2 == 0 {
					metrics.RecordJobCompleted(ctx, agentID, webhookID, duration)
				} else {
					metrics.RecordJobFailed(ctx, agentID, webhookID, "error", duration)
				}

				done <- true
			}(i)
		}

		// Wait for all goroutines
		for i := 0; i < 10; i++ {
			<-done
		}
	})
}

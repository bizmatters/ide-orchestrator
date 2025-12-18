package metrics

import (
	"context"
	"time"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/metric"
)

var meter = otel.Meter("job-metrics")

// JobMetrics provides metrics collection for job execution
type JobMetrics struct {
	jobsCreatedCounter    metric.Int64Counter
	jobsCompletedCounter  metric.Int64Counter
	jobsFailedCounter     metric.Int64Counter
	jobDurationHistogram  metric.Float64Histogram
	jobsActiveGauge       metric.Int64UpDownCounter
}

// NewJobMetrics creates a new job metrics collector
func NewJobMetrics() (*JobMetrics, error) {
	jobsCreatedCounter, err := meter.Int64Counter(
		"agent_builder.jobs.created",
		metric.WithDescription("Total number of jobs created"),
		metric.WithUnit("{job}"),
	)
	if err != nil {
		return nil, err
	}

	jobsCompletedCounter, err := meter.Int64Counter(
		"agent_builder.jobs.completed",
		metric.WithDescription("Total number of jobs completed successfully"),
		metric.WithUnit("{job}"),
	)
	if err != nil {
		return nil, err
	}

	jobsFailedCounter, err := meter.Int64Counter(
		"agent_builder.jobs.failed",
		metric.WithDescription("Total number of jobs that failed"),
		metric.WithUnit("{job}"),
	)
	if err != nil {
		return nil, err
	}

	jobDurationHistogram, err := meter.Float64Histogram(
		"agent_builder.job.duration",
		metric.WithDescription("Duration of job execution in seconds"),
		metric.WithUnit("s"),
	)
	if err != nil {
		return nil, err
	}

	jobsActiveGauge, err := meter.Int64UpDownCounter(
		"agent_builder.jobs.active",
		metric.WithDescription("Number of currently active jobs"),
		metric.WithUnit("{job}"),
	)
	if err != nil {
		return nil, err
	}

	return &JobMetrics{
		jobsCreatedCounter:   jobsCreatedCounter,
		jobsCompletedCounter: jobsCompletedCounter,
		jobsFailedCounter:    jobsFailedCounter,
		jobDurationHistogram: jobDurationHistogram,
		jobsActiveGauge:      jobsActiveGauge,
	}, nil
}

// RecordJobCreated records a new job creation
func (jm *JobMetrics) RecordJobCreated(ctx context.Context, agentID, webhookID string) {
	jm.jobsCreatedCounter.Add(ctx, 1,
		metric.WithAttributes(
			attribute.String("agent.id", agentID),
			attribute.String("webhook.id", webhookID),
		),
	)
	jm.jobsActiveGauge.Add(ctx, 1,
		metric.WithAttributes(
			attribute.String("agent.id", agentID),
		),
	)
}

// RecordJobCompleted records a successful job completion
func (jm *JobMetrics) RecordJobCompleted(ctx context.Context, agentID, webhookID string, duration time.Duration) {
	jm.jobsCompletedCounter.Add(ctx, 1,
		metric.WithAttributes(
			attribute.String("agent.id", agentID),
			attribute.String("webhook.id", webhookID),
			attribute.String("status", "completed"),
		),
	)
	jm.jobDurationHistogram.Record(ctx, duration.Seconds(),
		metric.WithAttributes(
			attribute.String("agent.id", agentID),
			attribute.String("webhook.id", webhookID),
			attribute.String("status", "completed"),
		),
	)
	jm.jobsActiveGauge.Add(ctx, -1,
		metric.WithAttributes(
			attribute.String("agent.id", agentID),
		),
	)
}

// RecordJobFailed records a failed job execution
func (jm *JobMetrics) RecordJobFailed(ctx context.Context, agentID, webhookID, errorType string, duration time.Duration) {
	jm.jobsFailedCounter.Add(ctx, 1,
		metric.WithAttributes(
			attribute.String("agent.id", agentID),
			attribute.String("webhook.id", webhookID),
			attribute.String("status", "failed"),
			attribute.String("error.type", errorType),
		),
	)
	jm.jobDurationHistogram.Record(ctx, duration.Seconds(),
		metric.WithAttributes(
			attribute.String("agent.id", agentID),
			attribute.String("webhook.id", webhookID),
			attribute.String("status", "failed"),
		),
	)
	jm.jobsActiveGauge.Add(ctx, -1,
		metric.WithAttributes(
			attribute.String("agent.id", agentID),
		),
	)
}

# Payments Orders System with Cassandra and Data Generation

## Project Overview
Build a local payments orders system with microservices architecture, automatic data generation, and Cassandra storage to teach Data Engineering concepts through production-grade implementation.

## Microservices Architecture
**Services:**
1. **Orders Service** - Order lifecycle management (create, update, status tracking)
2. **Payments Service** - Payment processing and validation
3. **Customers Service** - Customer data management
4. **Analytics Service** - Order statistics and reporting
5. **Data Pipeline Service** - Orchestration and monitoring

**Data Flow:**
- Event-driven architecture with synchronous fallback
- OrdersService publishes OrderCreated events
- PaymentsService, AnalyticsService subscribe to events
- Local message broker (RabbitMQ/Redis Streams) for event streaming

## Cassandra Schema Design
**Tables:**
1. **orders_table** - Partition by order_id, clustering by created_at
2. **payments_table** - Partition by order_id, clustering by payment_timestamp
3. **customers_table** - Partition by customer_id
4. **order_events_table** - Partition by order_id, clustering by event_timestamp

**Key Design Decisions:**
- Optimized for both transactional queries and time-series analytics
- Support for fast lookups by order_id and queries by customer_id
- Event tracking for audit trails and analytics

## Data Generation Engine
**Realistic Data Patterns:**
- Sequential order IDs with timestamp-based generation
- Valid customer relationships with realistic demographics
- Monetary amounts with proper decimal precision
- Multiple payment methods (credit card, PayPal, bank transfer)
- Order statuses: pending, processing, completed, cancelled, refunded

**Edge Cases Included:**
- Zero-value orders
- Refund scenarios
- Payment failures and retries
- Invalid customer references
- Duplicate order attempts
- High-value orders for testing performance

**Generation Schedule:**
- Burst periods during business hours
- Steady state during off-peak hours
- Weekend variations
- Load testing scenarios

## Technology Stack
**Framework:**
- FastAPI for all API services (async/await, automatic docs)
- SQLAlchemy for database access with async support
- Pydantic for data validation and serialization
- Dependency injection for service composition

**Cassandra:**
- Async driver (cassandra-driver)
- Connection pooling and retry policies
- Data center awareness for local deployment

**Local Infrastructure:**
- Docker Compose for service orchestration
- RabbitMQ for event streaming
- Redis for caching and session management
- Prometheus + Grafana for monitoring

## Error Handling and Resilience
**Circuit Breaker Pattern:**
- Fallback mechanisms for service unavailability
- Graceful degradation during Cassandra outages
- Dead letter queues for failed processing

**Structured Logging:**
- Correlation IDs for request tracing
- Structured log format with JSON
- Log levels appropriate for each scenario

**Error Categories:**
- Validation errors (input validation)
- Business logic errors (insufficient balance, invalid status)
- System errors (database connection failures)
- External service errors (payment gateway failures)

## Local Development Setup
docker-compose.yml:
- Cassandra with 3-node cluster
- RabbitMQ for event streaming
- Redis for caching
- All services on localhost ports

Development Scripts:
- Setup script to initialize Cassandra schema
- Data generation script with configurable scenarios
- Local API documentation generation
- Monitoring dashboard setup

## Testing Strategy
**Unit Tests:**
- Service layer business logic testing
- Data validation testing
- Error scenario testing

**Integration Tests:**
- Service-to-service communication testing
- Cassandra data consistency testing
- Event flow validation

**Data Quality Tests:**
- Schema validation testing
- Data integrity testing
- Performance testing under load

## Development Workflow
1. `docker-compose up -d` - Start local infrastructure
2. `./scripts/setup_cassandra.sh` - Initialize database
3. `./scripts/generate_data.py` - Generate test data
4. `python -m pip install -r requirements.txt` - Install dependencies
5. `uvicorn service:app --reload` - Run individual services
6. `./scripts/run_tests.sh` - Execute test suite
7. `./scripts/validate_data.py` - Data quality checks

## Success Metrics
- All services operational with event-driven communication
- Data generation produces realistic test data with edge cases
- Cassandra schema optimized for queries
- Error handling covers all failure scenarios
- Local deployment works without external dependencies
- Comprehensive monitoring and observability
- Automated testing validates functionality

This plan provides a production-ready system that teaches Data Engineering concepts through local development, with all microservices, data generation, and infrastructure components working together in a controlled environment.
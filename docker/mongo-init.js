// MongoDB initialization script
// This runs when the MongoDB container starts for the first time

db = db.getSiblingDB('research_assistant');

// Create collections with schema validation
db.createCollection('research_sessions', {
    validator: {
        $jsonSchema: {
            bsonType: 'object',
            required: ['session_id', 'query', 'status', 'created_at'],
            properties: {
                session_id: {
                    bsonType: 'string',
                    description: 'Unique session identifier'
                },
                query: {
                    bsonType: 'string',
                    description: 'Research query'
                },
                status: {
                    enum: ['queued', 'in_progress', 'completed', 'failed', 'cancelled'],
                    description: 'Session status'
                },
                created_at: {
                    bsonType: 'date',
                    description: 'Creation timestamp'
                }
            }
        }
    }
});

db.createCollection('sources');
db.createCollection('findings');
db.createCollection('reports');
db.createCollection('agent_logs');
db.createCollection('users');

// Create indexes for better query performance
db.research_sessions.createIndex({ 'session_id': 1 }, { unique: true });
db.research_sessions.createIndex({ 'status': 1 });
db.research_sessions.createIndex({ 'created_at': -1 });
db.research_sessions.createIndex({ 'query': 'text' });

db.sources.createIndex({ 'session_id': 1 });
db.sources.createIndex({ 'url': 1 });
db.sources.createIndex({ 'api_source': 1 });

db.findings.createIndex({ 'session_id': 1 });
db.findings.createIndex({ 'finding_type': 1 });
db.findings.createIndex({ 'verified': 1 });

db.reports.createIndex({ 'session_id': 1 }, { unique: true });

db.agent_logs.createIndex({ 'session_id': 1 });
db.agent_logs.createIndex({ 'agent_name': 1 });
db.agent_logs.createIndex({ 'created_at': -1 });

db.users.createIndex({ 'email': 1 }, { unique: true, sparse: true });

print('MongoDB initialization completed successfully!');

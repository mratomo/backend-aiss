# Database Integration Examples

This document provides practical examples of using the database integration features in AISS, including code samples for managing connections, agents, and executing queries against databases.

## Table of Contents

1. [Connection Management](#1-connection-management)
2. [Agent Configuration](#2-agent-configuration)
3. [Natural Language Database Queries](#3-natural-language-database-queries)
4. [Hybrid Queries (Documents + Databases)](#4-hybrid-queries-documents--databases)
5. [Programmatic Integration](#5-programmatic-integration)

## 1. Connection Management

### Creating a Database Connection

**curl:**
```bash
curl -X POST http://localhost:8080/api/v1/db-connections \
  -H "Authorization: Bearer TOKEN_ADMIN_AQUI" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Production PostgreSQL",
    "type": "postgresql",
    "host": "postgres.example.com",
    "port": 5432,
    "database": "production_db",
    "username": "readonly_user",
    "password": "secure_password",
    "ssl": true,
    "description": "Production database for sales and inventory",
    "tags": ["production", "sales", "inventory"]
  }'
```

**Python:**
```python
import requests

def create_db_connection(token, connection_data):
    url = "http://localhost:8080/api/v1/db-connections"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    response = requests.post(url, headers=headers, json=connection_data)
    return response.json()

# Usage
admin_token = "your_admin_token_here"
connection_data = {
    "name": "Production PostgreSQL",
    "type": "postgresql",
    "host": "postgres.example.com",
    "port": 5432,
    "database": "production_db",
    "username": "readonly_user",
    "password": "secure_password",
    "ssl": True,
    "description": "Production database for sales and inventory",
    "tags": ["production", "sales", "inventory"]
}

result = create_db_connection(admin_token, connection_data)
print(f"Connection created: {result['id']} - {result['name']}")
```

### Testing a Connection

**curl:**
```bash
curl -X POST http://localhost:8080/api/v1/db-connections/conn123/test \
  -H "Authorization: Bearer TOKEN_ADMIN_AQUI"
```

**JavaScript:**
```javascript
async function testDatabaseConnection(token, connectionId) {
  const url = `http://localhost:8080/api/v1/db-connections/${connectionId}/test`;
  
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`
    }
  });
  
  return await response.json();
}

// Usage
const adminToken = localStorage.getItem('adminToken');
const connectionId = 'conn123';

testDatabaseConnection(adminToken, connectionId)
  .then(result => {
    console.log(`Connection status: ${result.status}`);
    console.log(`Test time: ${result.elapsed_ms}ms`);
    if (result.error) {
      console.error(`Error: ${result.error}`);
    }
  })
  .catch(error => {
    console.error('Error testing connection:', error);
  });
```

### Listing Database Connections

**curl:**
```bash
curl -X GET http://localhost:8080/api/v1/db-connections \
  -H "Authorization: Bearer TOKEN_ADMIN_AQUI"
```

**Go:**
```go
package main

import (
	"encoding/json"
	"fmt"
	"net/http"
)

func listDatabaseConnections(token string) {
	url := "http://localhost:8080/api/v1/db-connections"
	
	// Create request
	req, _ := http.NewRequest("GET", url, nil)
	req.Header.Set("Authorization", "Bearer "+token)
	
	// Send request
	client := &http.Client{}
	resp, err := client.Do(req)
	if err != nil {
		fmt.Println("Error:", err)
		return
	}
	defer resp.Body.Close()
	
	// Process response
	var connections []map[string]interface{}
	json.NewDecoder(resp.Body).Decode(&connections)
	
	fmt.Println("Available Database Connections:")
	for _, conn := range connections {
		fmt.Printf("ID: %s\n", conn["id"])
		fmt.Printf("Name: %s\n", conn["name"])
		fmt.Printf("Type: %s\n", conn["type"])
		fmt.Printf("Status: %s\n", conn["status"])
		fmt.Println("---")
	}
}
```

## 2. Agent Configuration

### Creating a Database Agent

**curl:**
```bash
curl -X POST http://localhost:8080/api/v1/db-agents \
  -H "Authorization: Bearer TOKEN_ADMIN_AQUI" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Sales Analytics Agent",
    "description": "Agent for sales data analysis and reporting",
    "type": "db-only",
    "model_id": "llm123",
    "allowed_operations": ["SELECT"],
    "max_result_size": 500,
    "query_timeout_secs": 30,
    "default_system_prompt": "You are a helpful assistant that converts natural language questions about sales data into SQL queries. Only use the tables and columns provided in the schema. Always explain the results."
  }'
```

**Python:**
```python
import requests

def create_db_agent(token, agent_data):
    url = "http://localhost:8080/api/v1/db-agents"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    response = requests.post(url, headers=headers, json=agent_data)
    return response.json()

# Usage
admin_token = "your_admin_token_here"
agent_data = {
    "name": "Sales Analytics Agent",
    "description": "Agent for sales data analysis and reporting",
    "type": "db-only",
    "model_id": "llm123",
    "allowed_operations": ["SELECT"],
    "max_result_size": 500,
    "query_timeout_secs": 30,
    "default_system_prompt": "You are a helpful assistant that converts natural language questions about sales data into SQL queries. Only use the tables and columns provided in the schema. Always explain the results."
}

result = create_db_agent(admin_token, agent_data)
print(f"Agent created: {result['id']} - {result['name']}")
```

### Assigning a Connection to an Agent

**curl:**
```bash
curl -X POST http://localhost:8080/api/v1/db-agents/agent123/connections \
  -H "Authorization: Bearer TOKEN_ADMIN_AQUI" \
  -H "Content-Type: application/json" \
  -d '{
    "connection_id": "conn123",
    "permissions": ["SELECT"]
  }'
```

**JavaScript:**
```javascript
async function assignConnectionToAgent(token, agentId, connectionId, permissions) {
  const url = `http://localhost:8080/api/v1/db-agents/${agentId}/connections`;
  
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      connection_id: connectionId,
      permissions: permissions
    })
  });
  
  return await response.json();
}

// Usage
const adminToken = localStorage.getItem('adminToken');
const agentId = 'agent123';
const connectionId = 'conn123';
const permissions = ['SELECT'];

assignConnectionToAgent(adminToken, agentId, connectionId, permissions)
  .then(result => {
    console.log('Connection assigned to agent:', result);
  })
  .catch(error => {
    console.error('Error assigning connection:', error);
  });
```

### Updating Agent Prompts

**curl:**
```bash
curl -X PUT http://localhost:8080/api/v1/db-agents/agent123/prompts \
  -H "Authorization: Bearer TOKEN_ADMIN_AQUI" \
  -H "Content-Type: application/json" \
  -d '{
    "system_prompt": "You are a helpful assistant for sales data analysis...",
    "query_evaluation_prompt": "Determine if this query requires database access...",
    "query_generation_prompt": "Convert this natural language request to SQL...",
    "result_formatting_prompt": "Format the results of the SQL query in a readable way...",
    "example_db_queries": "Question: What were the total sales last month?\nSQL: SELECT SUM(amount) FROM sales WHERE date >= DATE_TRUNC('month', CURRENT_DATE - INTERVAL '1 month') AND date < DATE_TRUNC('month', CURRENT_DATE);"
  }'
```

**Python:**
```python
import requests

def update_agent_prompts(token, agent_id, prompts_data):
    url = f"http://localhost:8080/api/v1/db-agents/{agent_id}/prompts"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    response = requests.put(url, headers=headers, json=prompts_data)
    return response.json()

# Usage
admin_token = "your_admin_token_here"
agent_id = "agent123"
prompts_data = {
    "system_prompt": "You are a helpful assistant for sales data analysis...",
    "query_evaluation_prompt": "Determine if this query requires database access...",
    "query_generation_prompt": "Convert this natural language request to SQL...",
    "result_formatting_prompt": "Format the results of the SQL query in a readable way...",
    "example_db_queries": "Question: What were the total sales last month?\nSQL: SELECT SUM(amount) FROM sales WHERE date >= DATE_TRUNC('month', CURRENT_DATE - INTERVAL '1 month') AND date < DATE_TRUNC('month', CURRENT_DATE);"
}

result = update_agent_prompts(admin_token, agent_id, prompts_data)
print("Agent prompts updated successfully")
```

## 3. Natural Language Database Queries

### Basic Database Query

**curl:**
```bash
curl -X POST http://localhost:8080/api/v1/db-queries \
  -H "Authorization: Bearer TOKEN_AQUI" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "agent123",
    "query": "What were our total sales by region for the last quarter?",
    "options": {
      "max_results": 100
    }
  }'
```

**JavaScript:**
```javascript
async function performDatabaseQuery(token, agentId, queryText, options = {}) {
  const url = `http://localhost:8080/api/v1/db-queries`;
  
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      agent_id: agentId,
      query: queryText,
      options: options
    })
  });
  
  return await response.json();
}

// Usage
const token = localStorage.getItem('userToken');
const agentId = 'agent123';
const queryText = 'What were our total sales by region for the last quarter?';
const options = {
  max_results: 100
};

performDatabaseQuery(token, agentId, queryText, options)
  .then(result => {
    console.log('Query result:', result);
    
    // Display the answer
    document.getElementById('answer').textContent = result.answer;
    
    // Display the generated queries
    const queriesList = document.getElementById('generated-queries');
    queriesList.innerHTML = '';
    result.generated_queries.forEach(q => {
      const item = document.createElement('li');
      item.innerHTML = `<strong>${q.connection_name}</strong>: <code>${q.query_text}</code>`;
      queriesList.appendChild(item);
    });
    
    // Show execution time
    document.getElementById('execution-time').textContent = 
      `${result.execution_time_ms}ms`;
  })
  .catch(error => {
    console.error('Error performing query:', error);
  });
```

### Query with Specific Connections

**curl:**
```bash
curl -X POST http://localhost:8080/api/v1/db-queries \
  -H "Authorization: Bearer TOKEN_AQUI" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "agent123",
    "query": "Compare the average order value between our US and EU customers",
    "connections": ["conn_us", "conn_eu"],
    "options": {
      "include_schema_context": true
    }
  }'
```

**Python:**
```python
import requests

def perform_multi_db_query(token, agent_id, query_text, connection_ids, options=None):
    url = "http://localhost:8080/api/v1/db-queries"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "agent_id": agent_id,
        "query": query_text,
        "connections": connection_ids
    }
    
    if options:
        payload["options"] = options
    
    response = requests.post(url, headers=headers, json=payload)
    return response.json()

# Usage
token = "your_token_here"
agent_id = "agent123"
query = "Compare the average order value between our US and EU customers"
connections = ["conn_us", "conn_eu"]
options = {
    "include_schema_context": True
}

result = perform_multi_db_query(token, agent_id, query, connections, options)

print(f"Answer: {result['answer']}")
print("\nGenerated Queries:")
for query in result['generated_queries']:
    print(f"- {query['connection_name']}: {query['query_text']}")
print(f"\nExecution Time: {result['execution_time_ms']}ms")
```

### Query with Advanced Options

**curl:**
```bash
curl -X POST http://localhost:8080/api/v1/db-queries \
  -H "Authorization: Bearer TOKEN_AQUI" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "agent123",
    "query": "What are the top 10 customers by revenue, and what is their purchase history over the past year?",
    "options": {
      "max_results": 10,
      "include_charts": true,
      "format": "detailed",
      "timeout_seconds": 60,
      "include_raw_data": true
    }
  }'
```

**Go:**
```go
package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
)

type QueryOptions struct {
	MaxResults     int    `json:"max_results,omitempty"`
	IncludeCharts  bool   `json:"include_charts,omitempty"`
	Format         string `json:"format,omitempty"`
	TimeoutSeconds int    `json:"timeout_seconds,omitempty"`
	IncludeRawData bool   `json:"include_raw_data,omitempty"`
}

type QueryRequest struct {
	AgentID     string                 `json:"agent_id"`
	Query       string                 `json:"query"`
	Connections []string               `json:"connections,omitempty"`
	Options     QueryOptions           `json:"options,omitempty"`
}

func performAdvancedQuery(token string, request QueryRequest) {
	url := "http://localhost:8080/api/v1/db-queries"
	
	// Convert request to JSON
	jsonData, _ := json.Marshal(request)
	
	// Create request
	req, _ := http.NewRequest("POST", url, bytes.NewBuffer(jsonData))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+token)
	
	// Send request
	client := &http.Client{}
	resp, err := client.Do(req)
	if err != nil {
		fmt.Println("Error:", err)
		return
	}
	defer resp.Body.Close()
	
	// Process response
	var result map[string]interface{}
	json.NewDecoder(resp.Body).Decode(&result)
	
	// Print results
	fmt.Println("Query Answer:", result["answer"])
	
	// Print generated queries
	generatedQueries := result["generated_queries"].([]interface{})
	fmt.Println("\nGenerated Queries:")
	for _, q := range generatedQueries {
		query := q.(map[string]interface{})
		fmt.Printf("- %s: %s\n", query["connection_name"], query["query_text"])
	}
	
	// Print execution time
	fmt.Printf("\nExecution Time: %dms\n", int(result["execution_time_ms"].(float64)))
}

func main() {
	token := "your_token_here"
	
	request := QueryRequest{
		AgentID: "agent123",
		Query:   "What are the top 10 customers by revenue, and what is their purchase history over the past year?",
		Options: QueryOptions{
			MaxResults:     10,
			IncludeCharts:  true,
			Format:         "detailed",
			TimeoutSeconds: 60,
			IncludeRawData: true,
		},
	}
	
	performAdvancedQuery(token, request)
}
```

## 4. Hybrid Queries (Documents + Databases)

### Combining Document Knowledge with Database Data

**curl:**
```bash
curl -X POST http://localhost:8080/api/v1/queries \
  -H "Authorization: Bearer TOKEN_AQUI" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "How do our current product sales compare to the growth projections from last month's business plan?",
    "user_id": "user123",
    "include_personal": true,
    "area_ids": ["area_business_docs"],
    "db_agent_id": "agent123",
    "db_connections": ["conn_sales"],
    "max_sources": 5
  }'
```

**Python:**
```python
import requests

def perform_hybrid_query(token, query_text, user_id, document_area_ids, 
                         db_agent_id, db_connection_ids, options=None):
    url = "http://localhost:8080/api/v1/queries"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "query": query_text,
        "user_id": user_id,
        "include_personal": True,
        "area_ids": document_area_ids,
        "db_agent_id": db_agent_id,
        "db_connections": db_connection_ids,
        "max_sources": 5
    }
    
    if options:
        for key, value in options.items():
            payload[key] = value
    
    response = requests.post(url, headers=headers, json=payload)
    return response.json()

# Usage
token = "your_token_here"
query = "How do our current product sales compare to the growth projections from last month's business plan?"
user_id = "user123"
document_areas = ["area_business_docs"]
db_agent = "agent123"
db_connections = ["conn_sales"]

result = perform_hybrid_query(
    token, query, user_id, document_areas, db_agent, db_connections
)

print(f"Answer: {result['answer']}")

print("\nDocument Sources:")
for source in result['document_sources']:
    print(f"- {source['title']} (Score: {source['score']})")
    print(f"  {source['snippet']}")

print("\nDatabase Queries:")
for query in result['db_queries']:
    print(f"- {query['connection_name']}: {query['query_text']}")

print(f"\nProcessing Time: {result['processing_time_ms']}ms")
```

### Query with Data Comparison

**JavaScript:**
```javascript
async function performDataComparisonQuery(token, queryText, documentIds, dbAgentId) {
  const url = `http://localhost:8080/api/v1/queries/compare`;
  
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      query: queryText,
      document_ids: documentIds,
      db_agent_id: dbAgentId,
      comparison_type: "fact_checking",
      include_explanation: true
    })
  });
  
  return await response.json();
}

// Usage
const token = localStorage.getItem('userToken');
const queryText = "Verify if our actual Q2 sales match the projections in the quarterly forecast document";
const documentIds = ["doc123", "doc456"]; // IDs of quarterly forecast documents
const dbAgentId = "agent123"; // Agent with access to sales data

performDataComparisonQuery(token, queryText, documentIds, dbAgentId)
  .then(result => {
    console.log('Comparison result:', result);
    
    // Display the comparison analysis
    document.getElementById('comparison-result').innerHTML = result.analysis;
    
    // Display the facts verified
    const factsList = document.getElementById('verified-facts');
    factsList.innerHTML = '';
    result.verified_facts.forEach(fact => {
      const item = document.createElement('li');
      item.className = fact.is_consistent ? 'consistent' : 'inconsistent';
      item.innerHTML = `
        <div class="fact-statement">${fact.statement}</div>
        <div class="fact-source">Document: ${fact.document_source}</div>
        <div class="fact-data">Data: ${fact.data_value}</div>
        <div class="fact-result">${fact.is_consistent ? '✓ Consistent' : '✗ Inconsistent'}</div>
      `;
      factsList.appendChild(item);
    });
  })
  .catch(error => {
    console.error('Error performing comparison query:', error);
  });
```

## 5. Programmatic Integration

### Python SDK Example

```python
# pip install aiss-client

from aiss_client import AISS
from aiss_client.models import DBConnectionConfig, DBQuery

# Initialize client
client = AISS(
    base_url="http://localhost:8080",
    api_key="your_api_key_here"
)

# Create a database connection
connection = client.db_connections.create(
    name="Analytics Database",
    db_type="postgresql",
    host="analytics.example.com",
    port=5432,
    database="analytics",
    username="analyst",
    password="secure_password",
    ssl=True,
    tags=["analytics", "reporting"]
)
print(f"Created connection: {connection.id}")

# Test the connection
test_result = client.db_connections.test(connection.id)
print(f"Connection test: {test_result.status}")

# Create a database agent
agent = client.db_agents.create(
    name="Analytics Assistant",
    description="Natural language interface to analytics data",
    agent_type="db-only",
    model_id="gpt-4o",
    allowed_operations=["SELECT"],
    max_result_size=200
)
print(f"Created agent: {agent.id}")

# Assign connection to agent
assignment = client.db_agents.assign_connection(
    agent_id=agent.id,
    connection_id=connection.id,
    permissions=["SELECT"]
)
print(f"Connection assigned to agent")

# Perform a database query
result = client.db_queries.execute(
    agent_id=agent.id,
    query="What were our top 5 products by revenue last month?",
    options={
        "max_results": 5,
        "include_charts": True
    }
)

# Process the results
print(f"\nAnswer: {result.answer}")
print("\nGenerated SQL:")
for query in result.generated_queries:
    print(f"- {query.connection_name}: {query.query_text}")

print("\nData Results:")
for row in result.data:
    print(row)

# Generate and save chart
if result.chart:
    result.chart.save("top_products_chart.png")
    print("\nChart saved to top_products_chart.png")
```

### Node.js SDK Example

```javascript
// npm install aiss-node-client

const AISS = require('aiss-node-client');

async function main() {
  // Initialize client
  const client = new AISS({
    baseUrl: 'http://localhost:8080',
    apiKey: 'your_api_key_here'
  });
  
  try {
    // List available database connections
    const connections = await client.dbConnections.list();
    console.log(`Found ${connections.length} database connections`);
    
    // List available database agents
    const agents = await client.dbAgents.list();
    console.log(`Found ${agents.length} database agents`);
    
    if (agents.length === 0) {
      console.log('No agents available. Please create an agent first.');
      return;
    }
    
    // Choose the first agent
    const agent = agents[0];
    console.log(`Using agent: ${agent.name} (${agent.id})`);
    
    // Execute a database query
    const queryResult = await client.dbQueries.execute({
      agentId: agent.id,
      query: 'What was our revenue by product category for the last quarter?',
      options: {
        includeCharts: true,
        format: 'detailed'
      }
    });
    
    // Process the result
    console.log('\nQuery Answer:');
    console.log(queryResult.answer);
    
    console.log('\nGenerated Queries:');
    queryResult.generatedQueries.forEach(q => {
      console.log(`- ${q.connectionName}: ${q.queryText}`);
    });
    
    console.log('\nData Results:');
    console.table(queryResult.data);
    
    // Save chart if available
    if (queryResult.chart) {
      const fs = require('fs');
      fs.writeFileSync(
        'revenue_chart.png', 
        Buffer.from(queryResult.chart, 'base64')
      );
      console.log('\nChart saved to revenue_chart.png');
    }
    
    // Get query history
    const history = await client.dbQueries.getHistory({
      limit: 10,
      offset: 0
    });
    
    console.log('\nRecent Query History:');
    history.items.forEach((item, index) => {
      console.log(`${index + 1}. ${item.query} (${new Date(item.createdAt).toLocaleString()})`);
    });
    
  } catch (error) {
    console.error('Error:', error.message);
  }
}

main();
```

### Go SDK Example

```go
package main

import (
	"context"
	"fmt"
	"os"
	
	"github.com/example/aiss-go-client"
)

func main() {
	// Initialize client
	client, err := aiss.NewClient(
		aiss.WithBaseURL("http://localhost:8080"),
		aiss.WithAPIKey("your_api_key_here"),
	)
	if err != nil {
		fmt.Printf("Error initializing client: %v\n", err)
		os.Exit(1)
	}
	
	ctx := context.Background()
	
	// Get available agents
	agents, err := client.DBAgents.List(ctx, &aiss.ListOptions{})
	if err != nil {
		fmt.Printf("Error listing agents: %v\n", err)
		os.Exit(1)
	}
	
	if len(agents) == 0 {
		fmt.Println("No database agents available. Please create an agent first.")
		os.Exit(1)
	}
	
	// Use the first agent
	agent := agents[0]
	fmt.Printf("Using agent: %s (%s)\n", agent.Name, agent.ID)
	
	// Execute a database query
	queryResult, err := client.DBQueries.Execute(ctx, &aiss.DBQueryRequest{
		AgentID: agent.ID,
		Query:   "What are the sales trends for our top 5 products over the past year?",
		Options: map[string]interface{}{
			"includeCharts": true,
			"timeRange":     "1year",
			"groupBy":       "month",
		},
	})
	if err != nil {
		fmt.Printf("Error executing query: %v\n", err)
		os.Exit(1)
	}
	
	// Process results
	fmt.Println("\nQuery Answer:")
	fmt.Println(queryResult.Answer)
	
	fmt.Println("\nGenerated Queries:")
	for _, query := range queryResult.GeneratedQueries {
		fmt.Printf("- %s: %s\n", query.ConnectionName, query.QueryText)
	}
	
	fmt.Printf("\nExecution Time: %dms\n", queryResult.ExecutionTimeMs)
	
	// Process data
	fmt.Println("\nData Results:")
	fmt.Printf("Rows: %d\n", len(queryResult.Data))
	
	// Save chart if available
	if queryResult.Chart != nil {
		err = os.WriteFile("sales_trends.png", queryResult.Chart, 0644)
		if err != nil {
			fmt.Printf("Error saving chart: %v\n", err)
		} else {
			fmt.Println("\nChart saved to sales_trends.png")
		}
	}
}
```

These examples demonstrate the typical usage patterns for integrating with the database features of AISS. For more detailed examples, refer to the SDK documentation.
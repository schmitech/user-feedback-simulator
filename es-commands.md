# Elasticsearch Commands Reference

## Basic Operations

### Get Document Count
```http
GET /sentiment/_count
```

### Get Statistics
```http
GET /sentiment/_stats
```

### Delete Index
```http
DELETE /sentiment
```

### Create Index with Mappings
```http
PUT /sentiment
{
  "mappings": {
    "properties": {
      "reviewId": { "type": "keyword" },
      "timestamp": { "type": "long" },
      "reviewDateTime": { "type": "date" },
      "review": { "type": "text" },
      "title": { "type": "text" },
      "rating": { "type": "integer" },
      "recommended": { "type": "boolean" },
      "age": { "type": "integer" },
      "department": { "type": "keyword" },
      "division": { "type": "keyword" },
      "class": { "type": "keyword" },
      "clothingId": { "type": "keyword" },
      "randomBucket": { "type": "integer" },
      "sentiment": { "type": "keyword" },
      "sentimentScore": {
        "properties": {
          "Positive": { "type": "double" },
          "Negative": { "type": "double" },
          "Neutral": { "type": "double" },
          "Mixed": { "type": "double" }
        }
      },
      "keyPhrases": { "type": "keyword" },
      "processingTimestamp": { "type": "date" },
      "source": { "type": "keyword" }
    }
  }
}
```

## Queries

### Delete Documents Matching a Query
```http
POST /sentiment/_delete_by_query
{
  "query": {
    "match_all": {}
  }
}
```

### Search by Specific Field
```http
GET /sentiment/_search
{
  "query": {
    "term": {
      "reviewId": "0121bb76-853e-4efe-98fc-e9031db19be0"
    }
  }
}
```

### Match All Documents
```http
GET /sentiment/_search
{
  "query": {
    "match_all": {}
  }
}
```

### Search by Range
```http
GET /sentiment/_search
{
  "query": {
    "range": {
      "sentimentScore.Negative": {
        "gt": 0.95
      }
    }
  }
}
```

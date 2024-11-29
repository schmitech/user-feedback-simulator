GET /sentiment/_count

DELETE /sentiment

PUT /sentiment
```json
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

POST /sentiment/_delete_by_query
{
  "query": {
    "match_all": {}
  }
}

GET /sentiment/_search
{
  "query": {
    "match_all": {}
  }
}

GET /sentiment/_search
{
  "query": {
    "range": {
      "sentimentScore.Negative": {
        "gt": 0.95
      }
    }
  },
  "sort": [
    {
      "sentimentScore.Negative": {
        "order": "desc"
      }
    }
  ]
}
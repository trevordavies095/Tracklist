#!/bin/bash

BASE_URL="http://localhost:8000/api/v1/reports"

echo "Testing Reporting API Endpoints"
echo "================================"

echo -e "\n1. Testing Overview Statistics..."
curl -s "$BASE_URL/overview" | jq '.total_albums, .fully_rated_count, .average_album_score'

echo -e "\n2. Testing Recent Activity..."
curl -s "$BASE_URL/activity?limit=20" | jq '{recently_rated: .recently_rated | length, in_progress: .in_progress | length}'

echo -e "\n3. Testing Top Albums..."
curl -s "$BASE_URL/top-albums?limit=3" | jq '.[0:3] | .[] | {name: .name, score: .score}'

echo -e "\nAll tests completed!"
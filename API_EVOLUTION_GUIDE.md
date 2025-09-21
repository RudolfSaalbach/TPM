# API Evolution & Migration Guide

## Overview

This guide provides comprehensive information about API versioning, deprecation policies, and migration paths for the Chronos Engine v2.1 API.

## API Versioning Strategy

### Current Version Structure

- **v1 API**: `/api/v1/*` - Current stable API
- **Future v2 API**: `/api/v2/*` - Next major version (planned)

### Versioning Principles

1. **Semantic Versioning**: Major.Minor.Patch
2. **Backward Compatibility**: Minor versions maintain compatibility
3. **Deprecation Policy**: 6-month notice before removal
4. **Clear Migration Paths**: Documentation and tools for upgrades

## Deprecation Management

### Deprecation Levels

```typescript
enum DeprecationLevel {
  INFO = "info"           // Notice of future deprecation
  WARNING = "warning"     // Deprecated but still supported
  CRITICAL = "critical"   // Will be removed soon
  SUNSET = "sunset"       // Final warning before removal
}
```

### Deprecation Headers

All deprecated features include standardized headers:

```http
Deprecation: true
X-API-Deprecation-1-Feature: parameter:limit
X-API-Deprecation-1-Level: warning
X-API-Deprecation-1-Message: Parameter 'limit' is deprecated. Use 'page_size' instead.
X-API-Deprecation-1-Alternative: page_size parameter with page-based pagination
X-API-Deprecation-1-Removal-Date: 2024-06-01
```

## Migration Guide

### Phase 3 Changes (Current)

#### 1. Pagination Standardization

**Old (Deprecated):**
```http
GET /api/v1/events?limit=50&offset=100
```

**New (Recommended):**
```http
GET /api/v1/events?page=3&page_size=50
```

**Migration Steps:**
1. Replace `limit` with `page_size`
2. Calculate `page` from `offset`: `page = (offset / limit) + 1`
3. Update client code to handle pagination metadata

#### 2. Standardized Response Schemas

**Old (Mixed Formats):**
```json
{
  "calendars": [...],
  "total_count": 10
}
```

**New (Standardized):**
```json
{
  "success": true,
  "calendars": [...],
  "total_count": 10,
  "timestamp": "2024-01-01T12:00:00Z"
}
```

#### 3. Enhanced Error Responses

**Old (Inconsistent):**
```json
{
  "detail": "Error message"
}
```

**New (Structured):**
```json
{
  "success": false,
  "error": "Human-readable error message",
  "error_code": "VALIDATION_ERROR",
  "details": [
    {
      "field": "email",
      "message": "Invalid email format",
      "code": "value_error.email"
    }
  ],
  "timestamp": "2024-01-01T12:00:00Z",
  "request_id": "req_123e4567-e89b-12d3-a456-426614174000"
}
```

## Endpoint Changes

### CalDAV Endpoints

| Endpoint | Change | Migration |
|----------|--------|-----------|
| `GET /api/v1/caldav/backend/info` | Added response_model | Update client to expect structured response |
| `POST /api/v1/caldav/connection/test` | Standardized response | Use CalDAVConnectionTestResponse schema |
| `POST /api/v1/caldav/backend/switch` | Standardized response | Use CalDAVBackendSwitchResponse schema |

### Commands Endpoints

| Endpoint | Change | Migration |
|----------|--------|-----------|
| `GET /api/v1/commands/{system_id}` | Deprecated `limit` param | Use `page` and `page_size` instead |
| `POST /api/v1/commands/{command_id}/complete` | Standardized response | Use CommandOperationResponse schema |
| `POST /api/v1/commands/{command_id}/fail` | Standardized response | Use CommandOperationResponse schema |

### Admin Endpoints

| Endpoint | Change | Migration |
|----------|--------|-----------|
| `GET /api/v1/admin/system/info` | Standardized response | Use SystemInfoResponse schema |
| `GET /api/v1/admin/statistics` | Standardized response | Use AdminStatisticsResponse schema |
| `POST /api/v1/admin/calendar/repair` | Standardized response | Use CalendarRepairResponse schema |

### Sync Endpoints

| Endpoint | Change | Migration |
|----------|--------|-----------|
| `GET /api/v1/sync/status` | Enhanced response model | Use SyncStatusResponse schema |
| `GET /api/v1/sync/analytics/productivity` | Standardized response | Use ProductivityMetricsResponse schema |
| `POST /api/v1/sync/ai/optimize` | Standardized response | Use ScheduleOptimizationResponse schema |

## Client Migration Checklist

### 1. Update Pagination Logic

```typescript
// Old client code
const fetchEvents = (limit: number, offset: number) => {
  return api.get(`/events?limit=${limit}&offset=${offset}`);
};

// New client code
const fetchEvents = (page: number, pageSize: number) => {
  return api.get(`/events?page=${page}&page_size=${pageSize}`);
};
```

### 2. Handle Deprecation Headers

```typescript
// Add deprecation warning handler
api.interceptors.response.use(
  (response) => {
    if (response.headers['deprecation'] === 'true') {
      console.warn('Deprecated API feature used:', {
        feature: response.headers['x-api-deprecation-1-feature'],
        message: response.headers['x-api-deprecation-1-message'],
        alternative: response.headers['x-api-deprecation-1-alternative']
      });
    }
    return response;
  }
);
```

### 3. Update Error Handling

```typescript
// Old error handling
try {
  const response = await api.get('/events');
} catch (error) {
  console.error('API error:', error.response.data.detail);
}

// New error handling
try {
  const response = await api.get('/events');
} catch (error) {
  const errorData = error.response.data;
  console.error('API error:', {
    message: errorData.error,
    code: errorData.error_code,
    requestId: errorData.request_id,
    details: errorData.details
  });
}
```

### 4. Implement Request ID Tracking

```typescript
// Add request ID to all API calls for better debugging
api.interceptors.request.use((config) => {
  config.headers['X-Request-ID'] = generateUUID();
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const requestId = error.config.headers['X-Request-ID'];
    const errorRequestId = error.response?.data?.request_id;
    console.error(`Request ${requestId} failed:`, {
      serverRequestId: errorRequestId,
      error: error.response?.data
    });
    return Promise.reject(error);
  }
);
```

## Testing Migration

### 1. Gradual Migration Strategy

1. **Phase 1**: Update error handling and add deprecation warnings
2. **Phase 2**: Migrate pagination parameters
3. **Phase 3**: Update response handling for new schemas
4. **Phase 4**: Remove deprecated parameter usage

### 2. Feature Flag Approach

```typescript
const API_CONFIG = {
  useNewPagination: true,
  useStructuredErrors: true,
  trackRequestIds: true
};

const fetchEvents = async (page: number, pageSize: number) => {
  const params = API_CONFIG.useNewPagination
    ? { page, page_size: pageSize }
    : { limit: pageSize, offset: (page - 1) * pageSize };

  return api.get('/events', { params });
};
```

### 3. Automated Testing

```typescript
// Test for deprecation warnings
test('should warn about deprecated parameters', async () => {
  const response = await api.get('/events?limit=10&offset=0');
  expect(response.headers['deprecation']).toBe('true');
  expect(response.headers['x-api-deprecation-1-feature']).toContain('limit');
});

// Test new response schemas
test('should return structured error responses', async () => {
  try {
    await api.post('/events', { invalid: 'data' });
  } catch (error) {
    const errorData = error.response.data;
    expect(errorData).toHaveProperty('success', false);
    expect(errorData).toHaveProperty('error_code');
    expect(errorData).toHaveProperty('request_id');
  }
});
```

## Breaking Changes Schedule

### Planned for v1.1 (2024-06-01)

- ❌ Remove deprecated `limit` and `offset` parameters
- ❌ Remove deprecated `priority_filter` parameter
- ✅ Enforce structured response schemas

### Planned for v2.0 (2024-12-01)

- ❌ Remove legacy error format support
- ❌ Remove backward compatibility decorators
- ✅ New authentication system
- ✅ Enhanced filtering and search capabilities

## Support & Resources

### Documentation

- **API Reference**: `/docs` - Interactive OpenAPI documentation
- **Response Schemas**: `/docs#/schemas` - All standardized schemas
- **Error Codes**: `/docs#/errors` - Complete error code reference

### Migration Tools

- **Deprecation Scanner**: Tool to scan your code for deprecated API usage
- **Migration Assistant**: Automated code transformation tool
- **Compatibility Checker**: Validate your API calls against new schemas

### Support Channels

- **GitHub Issues**: Report bugs and request features
- **Discord Community**: Real-time support and discussions
- **Migration Assistance**: Dedicated support for large migrations

## Best Practices

### 1. Version Pinning

Always specify API version in your base URL:

```typescript
const API_BASE = 'https://api.chronos.com/api/v1';
```

### 2. Graceful Degradation

Handle both old and new response formats:

```typescript
const handleResponse = (data: any) => {
  // Support both old and new formats
  if (data.success !== undefined) {
    // New format
    return data.success ? data : handleError(data);
  } else {
    // Legacy format
    return data.error ? handleError(data) : data;
  }
};
```

### 3. Monitoring

Track API usage and deprecation warnings:

```typescript
// Monitor deprecation usage
const trackDeprecation = (feature: string, alternative: string) => {
  analytics.track('api_deprecation_used', {
    feature,
    alternative,
    timestamp: new Date().toISOString()
  });
};
```

### 4. Future-Proofing

Design your client code to be resilient to API changes:

```typescript
// Use optional chaining for new fields
const processResponse = (data: any) => {
  return {
    items: data.data || data.items || [],
    total: data.pagination?.total_items || data.total_count || 0,
    hasNext: data.pagination?.has_next || false
  };
};
```

## Conclusion

This migration guide ensures smooth transitions between API versions while maintaining system stability. Follow the recommended migration paths and timelines to avoid disruptions.

For questions or assistance, please refer to our support channels or create an issue in the project repository.
---
name: nextjs-app-router-route-conflict-prevention
description: "Skill for preventing and diagnosing Next.js App Router dynamic route conflicts where static path segments unintentionally match dynamic routes like [id], causing unexpected 404 errors"
metadata:
  author: autolearn-reviewer
  version: "0.1.0"
---

# Next.js App Router Dynamic Route Conflict Prevention

## Problem
In Next.js App Router, when you have a dynamic route like `/voicemaker/[id]/page.tsx` and navigate to `/voicemaker/onboarding`, the segment "onboarding" matches the dynamic `[id]` parameter. This causes the `PublicVoiceMakerProfile` component to attempt to load a profile with id="onboarding", which doesn't exist, triggering `notFound()` and resulting in a 404 error.

## Root Cause Analysis
1. User navigates to `/voicemaker/onboarding` (intended to show onboarding flow)
2. The route matches `/voicemaker/[id]` where `id="onboarding"`
3. The `PublicVoiceMakerProfile` component queries for a voicemaker with id="onboarding"
4. Since no such voicemaker exists, the component calls `notFound()`
5. This results in a 404 error despite the page returning 200 status (RSC payload contains the error)

## Diagnosis Steps
1. Check if you're seeing unexpected 404s on paths that should exist
2. Look for dynamic routes like `[id]` or `[slug]` in your app directory
3. Verify if static path segments (like "onboarding", "login", "settings") are being captured as dynamic parameters
4. Inspect components that use route parameters to fetch data - they may be calling `notFound()` when data isn't found
5. Check RSC payloads for `notFound` markers when debugging 404s

## Prevention Techniques
1. **Use pathname.startsWith(href + '/')** instead of `pathname.startsWith(href)` for non-exact matches to require path segment boundaries
2. **Add explicit static routes** before dynamic ones when possible (though App Router doesn't support route prioritization)
3. **Validate route parameters early** - check if the parameter value corresponds to a valid resource before proceeding
4. **Use dedicated route segments** - avoid generic names like `[id]` when more specific naming is possible
5. **Add middleware redirects** for known problematic static segments that should not be treated as dynamic parameters

## Example Fix
Instead of:
```typescript
if (pathname.startsWith('/voicemaker/')) {
  // This will match /voicemaker/onboarding and treat "onboarding" as an id
}
```

Use:
```typescript
if (pathname.startsWith('/voicemaker/') && pathname.length > '/voicemaker/'.length && pathname.charAt('/voicemaker/'.length) !== '/') {
  // Ensures we're matching /voicemaker/something where something is not empty
  // Still needs additional validation for your specific use case
}

// Or better yet, validate the parameter against known values
const validSections = ['onboarding', 'settings', 'dashboard'];
if (pathname.startsWith('/voicemaker/')) {
  const potentialId = pathname.substring('/voicemaker/'.length);
  if (!validSections.includes(potentialId)) {
    // Treat as a dynamic ID for voicemaker lookup
    const voicemakerId = potentialId;
    // ... fetch voicemaker data
  }
}
```

## Verification
1. Test navigation to static segments that could conflict with dynamic routes
2. Verify that components properly handle invalid route parameters (redirect, show error, etc.)
3. Check that legitimate dynamic route parameters still work correctly
4. Monitor for `notFound()` calls in components that shouldn't be triggering them

## Related Knowledge
- This is a common issue in file-based routing systems where static and dynamic segments overlap
- Similar issues can occur with catch-all routes like `[...slug]`
- Always validate route parameters against expected values before using them for data fetching

/**
 * Cloudflare Worker - CrossTrans Trial Proxy
 *
 * Multi-provider fallback support:
 * Cerebras (primary) -> Groq (backup 1) -> SambaNova (backup 2)
 *
 * Setup:
 * 1. Create a Cloudflare Worker
 * 2. Paste this code
 * 3. Add environment variables:
 *    - CEREBRAS_API_KEY (required)
 *    - GROQ_API_KEY (optional, for fallback)
 *    - SAMBANOVA_API_KEY (optional, for fallback)
 * 4. Deploy
 */

// Rate limiting storage
const DAILY_LIMIT = 100;
const rateLimitCache = new Map();

// Provider configurations
const PROVIDERS = {
  cerebras: {
    name: 'Cerebras',
    url: 'https://api.cerebras.ai/v1/chat/completions',
    model: 'llama-3.3-70b',
    envKey: 'CEREBRAS_API_KEY',
  },
  groq: {
    name: 'Groq',
    url: 'https://api.groq.com/openai/v1/chat/completions',
    model: 'llama-3.3-70b-versatile',
    envKey: 'GROQ_API_KEY',
  },
  sambanova: {
    name: 'SambaNova',
    url: 'https://api.sambanova.ai/v1/chat/completions',
    model: 'Meta-Llama-3.3-70B-Instruct',
    envKey: 'SAMBANOVA_API_KEY',
  },
};

// Provider fallback order
const FALLBACK_ORDER = ['cerebras', 'groq', 'sambanova'];

export default {
  async fetch(request, env) {
    // CORS headers
    const corsHeaders = {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, X-Device-ID',
    };

    // Handle preflight
    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: corsHeaders });
    }

    // Only allow POST
    if (request.method !== 'POST') {
      return new Response(JSON.stringify({ error: 'Method not allowed' }), {
        status: 405,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }

    try {
      // Get device ID for rate limiting
      const deviceId = request.headers.get('X-Device-ID') || 'unknown';

      // Check rate limit
      const rateLimitResult = checkRateLimit(deviceId);
      if (!rateLimitResult.allowed) {
        return new Response(JSON.stringify({
          error: 'Daily quota exceeded. Please add your own API key.',
          remaining: 0
        }), {
          status: 429,
          headers: { ...corsHeaders, 'Content-Type': 'application/json' }
        });
      }

      // Parse request body
      const body = await request.json();

      // Validate request
      if (!body.messages || !Array.isArray(body.messages)) {
        return new Response(JSON.stringify({ error: 'Invalid request format' }), {
          status: 400,
          headers: { ...corsHeaders, 'Content-Type': 'application/json' }
        });
      }

      // Try providers in fallback order
      let lastError = null;
      let usedProvider = null;

      for (const providerId of FALLBACK_ORDER) {
        const provider = PROVIDERS[providerId];
        const apiKey = env[provider.envKey];

        // Skip if no API key configured for this provider
        if (!apiKey) {
          continue;
        }

        try {
          console.log(`Trying provider: ${provider.name}`);

          const response = await fetch(provider.url, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'Authorization': `Bearer ${apiKey}`,
            },
            body: JSON.stringify({
              model: body.model || provider.model,
              messages: body.messages,
              temperature: body.temperature || 0.3,
              max_tokens: body.max_tokens || 4096,
            }),
          });

          if (response.ok) {
            const result = await response.json();

            // Success! Increment rate limit counter
            incrementRateLimit(deviceId);
            usedProvider = provider.name;

            return new Response(JSON.stringify(result), {
              status: 200,
              headers: {
                ...corsHeaders,
                'Content-Type': 'application/json',
                'X-Remaining-Quota': String(DAILY_LIMIT - getRateLimitCount(deviceId)),
                'X-Provider-Used': usedProvider,
              }
            });
          }

          // Provider returned error, try next
          const errorText = await response.text();
          console.error(`${provider.name} error (${response.status}): ${errorText}`);
          lastError = `${provider.name}: ${response.status}`;

        } catch (providerError) {
          // Network or other error, try next provider
          console.error(`${provider.name} failed:`, providerError.message);
          lastError = `${provider.name}: ${providerError.message}`;
        }
      }

      // All providers failed
      return new Response(JSON.stringify({
        error: 'All translation providers are temporarily unavailable. Please try again later.',
        details: lastError
      }), {
        status: 502,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });

    } catch (error) {
      console.error('Worker error:', error);
      return new Response(JSON.stringify({ error: 'Internal server error' }), {
        status: 500,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }
  }
};

// Simple in-memory rate limiting (resets when worker restarts)
// For production, use Cloudflare KV or D1 database
function checkRateLimit(deviceId) {
  const today = new Date().toISOString().split('T')[0];
  const key = `${deviceId}:${today}`;
  const count = rateLimitCache.get(key) || 0;

  return {
    allowed: count < DAILY_LIMIT,
    remaining: Math.max(0, DAILY_LIMIT - count)
  };
}

function incrementRateLimit(deviceId) {
  const today = new Date().toISOString().split('T')[0];
  const key = `${deviceId}:${today}`;
  const count = rateLimitCache.get(key) || 0;
  rateLimitCache.set(key, count + 1);

  // Clean old entries (simple cleanup)
  for (const [k] of rateLimitCache) {
    if (!k.endsWith(today)) {
      rateLimitCache.delete(k);
    }
  }
}

function getRateLimitCount(deviceId) {
  const today = new Date().toISOString().split('T')[0];
  const key = `${deviceId}:${today}`;
  return rateLimitCache.get(key) || 0;
}

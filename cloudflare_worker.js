/**
 * Cloudflare Worker - CrossTrans Trial Proxy
 *
 * Multi-provider fallback support (in order):
 * 1. Cerebras (llama-3.3-70b)
 * 2. SambaNova (llama-3.3-70b)
 * 3. Groq (llama-3.3-70b)
 * 4. Gemini Free (gemini-2.5-flash-lite)
 * 5. Gemini Paid (gemini-2.5-flash-lite)
 *
 * Setup:
 * 1. Create a Cloudflare Worker
 * 2. Paste this code
 * 3. Add environment variables:
 *    - CEREBRAS_API_KEY (primary)
 *    - SAMBANOVA_API_KEY (fallback 1)
 *    - GROQ_API_KEY (fallback 2)
 *    - HUGGINGFACE_API_KEY (fallback 3)
 *    - GEMINI_API_KEY_FREE (fallback 4)
 *    - GEMINI_API_KEY_PAID (fallback 5)
 *    - SUPABASE_URL (optional - for analytics)
 *    - SUPABASE_SERVICE_KEY (optional - for analytics)
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
    type: 'openai',  // OpenAI-compatible API
  },
  sambanova: {
    name: 'SambaNova',
    url: 'https://api.sambanova.ai/v1/chat/completions',
    model: 'Meta-Llama-3.3-70B-Instruct',
    envKey: 'SAMBANOVA_API_KEY',
    type: 'openai',
  },
  groq: {
    name: 'Groq',
    url: 'https://api.groq.com/openai/v1/chat/completions',
    model: 'llama-3.3-70b-versatile',
    envKey: 'GROQ_API_KEY',
    type: 'openai',
  },
  huggingface: {
    name: 'HuggingFace',
    url: 'https://router.huggingface.co/v1/chat/completions',
    model: 'meta-llama/Llama-3.1-70B-Instruct',
    envKey: 'HUGGINGFACE_API_KEY',
    type: 'openai',
  },
  gemini_free: {
    name: 'Gemini (Free)',
    url: 'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent',
    model: 'gemini-2.5-flash-lite',
    envKey: 'GEMINI_API_KEY_FREE',
    type: 'gemini',  // Google Gemini API
  },
  gemini_paid: {
    name: 'Gemini (Paid)',
    url: 'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent',
    model: 'gemini-2.5-flash-lite',
    envKey: 'GEMINI_API_KEY_PAID',
    type: 'gemini',
  },
};

// Provider fallback order
const FALLBACK_ORDER = ['cerebras', 'sambanova', 'groq', 'huggingface', 'gemini_free', 'gemini_paid'];

// ============= SUPABASE ANALYTICS LOGGING =============
async function logToSupabase(env, logData) {
  // Only log if Supabase is configured
  if (!env.SUPABASE_URL || !env.SUPABASE_SERVICE_KEY) {
    return;
  }

  try {
    const response = await fetch(`${env.SUPABASE_URL}/rest/v1/usage_logs`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'apikey': env.SUPABASE_SERVICE_KEY,
        'Authorization': `Bearer ${env.SUPABASE_SERVICE_KEY}`,
        'Prefer': 'return=minimal'
      },
      body: JSON.stringify(logData)
    });

    if (!response.ok) {
      console.error('Supabase log failed:', response.status);
    }
  } catch (error) {
    // Don't throw - logging should not affect main request
    console.error('Supabase log error:', error.message);
  }
}

export default {
  async fetch(request, env) {
    // CORS headers
    const corsHeaders = {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, X-Device-ID, X-App-Context',
    };

    // Handle preflight
    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: corsHeaders });
    }

    // --- Remote Config endpoint (GET /v1/config) ---
    const url = new URL(request.url);
    if (url.pathname === '/v1/config' && request.method === 'GET') {
      try {
        const config = await env.MODELS_KV.get('models_config', 'json');
        if (!config) {
          return new Response(JSON.stringify({ error: 'Config not found' }), {
            status: 404,
            headers: { ...corsHeaders, 'Content-Type': 'application/json' }
          });
        }
        return new Response(JSON.stringify(config), {
          headers: {
            ...corsHeaders,
            'Content-Type': 'application/json',
            'Cache-Control': 'public, max-age=300',  // 5 min edge cache
          }
        });
      } catch (e) {
        return new Response(JSON.stringify({ error: 'Failed to read config', detail: e.message }), {
          status: 500,
          headers: { ...corsHeaders, 'Content-Type': 'application/json' }
        });
      }
    }

    // Only allow POST for translation endpoint
    if (request.method !== 'POST') {
      return new Response(JSON.stringify({ error: 'Method not allowed' }), {
        status: 405,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }

    try {
      // Get device ID for rate limiting
      const deviceId = request.headers.get('X-Device-ID') || 'unknown';
      const startTime = Date.now();

      // Validate app context
      const appContext = request.headers.get('X-App-Context');
      if (!appContext || appContext !== env.APP_CONTEXT) {
        return new Response(JSON.stringify({
          error: 'Unauthorized',
          message: 'Invalid request context'
        }), {
          status: 401,
          headers: { ...corsHeaders, 'Content-Type': 'application/json' }
        });
      }

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

          let response;
          let result;

          if (provider.type === 'gemini') {
            // Gemini API format
            response = await callGeminiAPI(provider, apiKey, body);
          } else {
            // OpenAI-compatible API format
            response = await callOpenAIAPI(provider, apiKey, body);
          }

          if (response.ok) {
            result = await response.json();

            // Convert Gemini response to OpenAI format if needed
            if (provider.type === 'gemini') {
              result = convertGeminiToOpenAI(result, provider.model);
            }

            // Success! Increment rate limit counter
            incrementRateLimit(deviceId);
            usedProvider = provider.name;

            // Log successful request to Supabase
            await logToSupabase(env, {
              device_id: deviceId,
              provider_used: usedProvider,
              success: true,
              prompt_tokens: result.usage?.prompt_tokens || 0,
              completion_tokens: result.usage?.completion_tokens || 0,
              total_tokens: result.usage?.total_tokens || 0,
              response_time_ms: Date.now() - startTime,
              ip_country: request.cf?.country || 'unknown'
            });

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

      // All providers failed - log failure to Supabase
      await logToSupabase(env, {
        device_id: deviceId,
        provider_used: null,
        success: false,
        error_message: lastError,
        response_time_ms: Date.now() - startTime,
        ip_country: request.cf?.country || 'unknown'
      });

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

// Call OpenAI-compatible API (Cerebras, SambaNova, Groq)
async function callOpenAIAPI(provider, apiKey, body) {
  return await fetch(provider.url, {
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
}

// Call Google Gemini API
async function callGeminiAPI(provider, apiKey, body) {
  // Convert OpenAI messages format to Gemini format
  const contents = convertMessagesToGemini(body.messages);

  const url = `${provider.url}?key=${apiKey}`;

  return await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      contents: contents,
      generationConfig: {
        temperature: body.temperature || 0.3,
        maxOutputTokens: body.max_tokens || 4096,
      },
    }),
  });
}

// Convert OpenAI messages to Gemini format
function convertMessagesToGemini(messages) {
  const contents = [];

  for (const msg of messages) {
    // Gemini uses 'user' and 'model' roles
    let role = msg.role;
    if (role === 'assistant') {
      role = 'model';
    } else if (role === 'system') {
      // Gemini doesn't have system role, prepend to first user message
      // For simplicity, treat as user message
      role = 'user';
    }

    contents.push({
      role: role,
      parts: [{ text: msg.content }]
    });
  }

  return contents;
}

// Convert Gemini response to OpenAI format
function convertGeminiToOpenAI(geminiResponse, model) {
  // Extract text from Gemini response
  let text = '';
  if (geminiResponse.candidates && geminiResponse.candidates[0]) {
    const candidate = geminiResponse.candidates[0];
    if (candidate.content && candidate.content.parts) {
      text = candidate.content.parts.map(p => p.text || '').join('');
    }
  }

  // Return OpenAI-compatible format
  return {
    id: `gemini-${Date.now()}`,
    object: 'chat.completion',
    created: Math.floor(Date.now() / 1000),
    model: model,
    choices: [{
      index: 0,
      message: {
        role: 'assistant',
        content: text,
      },
      finish_reason: 'stop',
    }],
    usage: {
      prompt_tokens: geminiResponse.usageMetadata?.promptTokenCount || 0,
      completion_tokens: geminiResponse.usageMetadata?.candidatesTokenCount || 0,
      total_tokens: geminiResponse.usageMetadata?.totalTokenCount || 0,
    }
  };
}

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

import { NextRequest, NextResponse } from "next/server";

const GEMINI_API_KEY = "AIzaSyDzfcUOrKaq2NhWgxgyHWrtfV3KGYF8jP0";

const MODELS = [
  "gemini-2.0-flash",
  "gemini-1.5-flash",
  "gemini-1.5-flash-latest",
];

const SYSTEM_PROMPT = `You are a Senior Pharmaceutical Regulatory Affairs expert specializing in ICH Q2(R2) and ICH Q14 compliance for analytical method validation. 

Review the JSON data below from an HPLC analytical method validation conducted using the SPARK (Sequential Predictive Analytical Risk Kernel) approach.

Write a highly technical, 3-paragraph executive summary justifying the immediate release of this validated analytical method:

Paragraph 1: Reference ICH Q2(R2) criteria met — specificity, linearity, accuracy, precision, range — supported by the FMEA risk assessment and RPN score.

Paragraph 2: Reference ICH Q14 enhanced approach — explain how the Bayesian Knowledge Graph fusion of historical prior data with current likelihood data provides a statistically rigorous justification for the reduced validation plan. Cite the prior influence percentage as mathematical proof.

Paragraph 3: Final conclusion — state that the method is validated and suitable for release based on the SPRT sequential analysis achieving ARRÊT POSITIF and the Monte Carlo probability exceeding the 97% ICH threshold.

Keep it strictly scientific, dense, and professional. Write in English. Do NOT use markdown formatting.`;

async function callGemini(model: string, sessionData: any): Promise<Response> {
  const url = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${GEMINI_API_KEY}`;
  
  return fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      contents: [
        {
          parts: [
            {
              text: `${SYSTEM_PROMPT}\n\n--- VALIDATION DATA ---\n${JSON.stringify(sessionData, null, 2)}`
            }
          ]
        }
      ],
      generationConfig: {
        temperature: 0.3,
        maxOutputTokens: 1024,
      }
    })
  });
}

async function sleep(ms: number) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

export async function POST(request: NextRequest) {
  try {
    const sessionData = await request.json();

    // Try each model with retry on rate limit
    for (const model of MODELS) {
      for (let attempt = 0; attempt < 3; attempt++) {
        console.log(`[Dossier] Trying ${model}, attempt ${attempt + 1}`);
        
        const response = await callGemini(model, sessionData);

        if (response.ok) {
          const result = await response.json();
          const generatedText =
            result?.candidates?.[0]?.content?.parts?.[0]?.text ||
            "No content generated.";
          
          console.log(`[Dossier] Success with ${model}`);
          return NextResponse.json({ summary: generatedText });
        }

        if (response.status === 429) {
          // Rate limited — wait and retry
          const waitMs = (attempt + 1) * 2000;
          console.log(`[Dossier] Rate limited (429), waiting ${waitMs}ms...`);
          await sleep(waitMs);
          continue;
        }

        // Other error — try next model
        const errorText = await response.text();
        console.error(`[Dossier] ${model} failed (${response.status}):`, errorText);
        break;
      }
    }

    // All models failed
    return NextResponse.json(
      { error: "All Gemini models failed. Please try again in a few seconds." },
      { status: 502 }
    );
  } catch (error: any) {
    console.error("[Dossier] Internal error:", error);
    return NextResponse.json(
      { error: "Internal server error", details: error.message },
      { status: 500 }
    );
  }
}

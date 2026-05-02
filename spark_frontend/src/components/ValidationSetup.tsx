"use client";

import React, { useState, useRef } from "react";

type DropzoneState = "idle" | "extracting" | "success" | "error";

interface FMEAState {
  maturite: number | null;
  matrice: number | null;
  donnees: number | null;
  criticite: number | null;
  risque: number | null;
}

interface ValidationSetupProps {
  onComplete?: (data: FMEAState) => void;
  // Lifted state from parent so it persists across tab switches
  dropState: DropzoneState;
  setDropState: (state: DropzoneState) => void;
  filename: string;
  setFilename: (name: string) => void;
  fmeaState: FMEAState;
  setFmeaState: (state: FMEAState | ((prev: FMEAState) => FMEAState)) => void;
  drugName: string;
  setDrugName: (name: string) => void;
}

export default function ValidationSetup({ 
  onComplete, 
  dropState, setDropState, 
  filename, setFilename,
  fmeaState, setFmeaState,
  drugName, setDrugName
}: ValidationSetupProps) {

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const isFormValid = Object.values(fmeaState).every((val) => val !== null);

  // ─── Real file upload handler ───
  const handleFileUpload = async (file: File) => {
    // Validate file type
    if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
      setErrorMsg("Type de fichier invalide. Seuls les PDF sont acceptés.");
      setTimeout(() => setErrorMsg(""), 4000);
      return;
    }

    setDropState("extracting");
    setErrorMsg("");

    try {
      const formData = new FormData();
      formData.append("file", file);

      // Do NOT set Content-Type header — browser handles multipart boundary automatically
      const response = await fetch("https://aec-2nd-phase-spark-team-prototype.onrender.com/spark/extract", {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const errBody = await response.json().catch(() => ({ detail: "Unknown error" }));
        throw new Error(errBody.detail || `Server returned ${response.status}`);
      }

      const data = await response.json();

      // Auto-fill the FMEA form with the API response
      const extractedData: FMEAState = {
        maturite: data.fmea_data.maturite,
        matrice: data.fmea_data.matrice,
        donnees: data.fmea_data.donnees,
        criticite: data.fmea_data.criticite,
        risque: data.fmea_data.risque,
      };
      setFmeaState(extractedData);
      setFilename(data.filename);
      setDrugName(data.drug_name || "Unknown Protocol");
      setDropState("success");

      // Console log all extracted data
      console.log("═══════════════════════════════════════════");
      console.log("  SPARK — PDF Extraction Complete (Backend)");
      console.log("═══════════════════════════════════════════");
      console.log("📄 Source File:", data.filename);
      console.log("📦 File Size:", data.file_size_kb, "KB");
      console.log("📊 Extracted FMEA Axes:", extractedData);
      console.log("  → Maturité:", extractedData.maturite);
      console.log("  → Matrice:", extractedData.matrice);
      console.log("  → Données:", extractedData.donnees);
      console.log("  → Criticité:", extractedData.criticite);
      console.log("  → Risque:", extractedData.risque);
      console.log("═══════════════════════════════════════════");

    } catch (error: any) {
      console.error("❌ PDF Extraction Error:", error);
      setDropState("idle");
      setErrorMsg(error.message || "Échec de l'extraction du PDF.");
      setTimeout(() => setErrorMsg(""), 5000);
    }
  };

  // Handle drag & drop
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (dropState === "extracting") return;

    const droppedFile = e.dataTransfer?.files?.[0];
    if (droppedFile) {
      handleFileUpload(droppedFile);
    }
  };

  // Handle click → open file picker
  const handleClick = () => {
    if (dropState === "extracting") return;
    // If already uploaded, allow re-upload by resetting
    if (dropState === "success") {
      setDropState("idle");
    }
    fileInputRef.current?.click();
  };

  // Handle file picker change
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0];
    if (selectedFile) {
      handleFileUpload(selectedFile);
    }
    // Reset input so the same file can be re-selected
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleSubmit = async () => {
    if (!isFormValid || isSubmitting) return;
    setIsSubmitting(true);

    // Console log the final submission data
    console.log("═══════════════════════════════════════════");
    console.log("  SPARK — Submitting FMEA to Backend");
    console.log("═══════════════════════════════════════════");
    console.log("📤 Payload:", {
      maturite_methode: fmeaState.maturite,
      complexite_matrice: fmeaState.matrice,
      disponibilite_donnees: fmeaState.donnees,
      criticite_reglementaire: fmeaState.criticite,
      risque_patient: fmeaState.risque
    });

    try {
      // 1. Calculate the math locally as requested
      const rpnScore = (fmeaState.maturite || 0) + 
                       (fmeaState.matrice || 0) + 
                       (fmeaState.donnees || 0) + 
                       (fmeaState.criticite || 0) + 
                       (fmeaState.risque || 0);

      let decision = "";
      if (rpnScore >= 5 && rpnScore <= 7) {
        decision = "PLAN LEVERAGED (3 niveaux x 2 réplicats = 6 injections)";
      } else if (rpnScore >= 8 && rpnScore <= 11) {
        decision = "PLAN RÉDUIT (4 niveaux x 2 réplicats = 8 injections)";
      } else {
        decision = "PLAN COMPLET (5 niveaux x 3 réplicats = 15 injections)";
      }

      console.log("✅ Client-side FMEA Math:");
      console.log("  → RPN:", rpnScore);
      console.log("  → Decision:", decision);
      console.log("═══════════════════════════════════════════");

      // 2. Pass structured object to parent
      onComplete?.({
        rawValues: fmeaState,
        rpnScore: rpnScore,
        decision: decision
      } as any);

    } catch (err) {
      console.error("❌ FMEA Error:", err);
      onComplete?.({
        rawValues: fmeaState,
        rpnScore: 5,
        decision: "Error calculating plan"
      } as any);
    } finally {
      setIsSubmitting(false);
    }
  };

  const SegmentControl = ({ label, description, axis }: { label: string, description: string, axis: keyof FMEAState }) => {
    return (
      <div className="flex items-center justify-between py-4 border-b border-hairline/50 last:border-0 group">
        <div>
          <div className="text-sm font-medium text-ink group-hover:text-primary transition-colors">{label}</div>
          <div className="text-[13px] text-ink-subtle">{description}</div>
        </div>
        
        <div className="flex items-center bg-canvas rounded-md p-1 border border-hairline shadow-inner">
          {[1, 2, 3].map((val) => {
            const isSelected = fmeaState[axis] === val;
            return (
              <button
                key={val}
                onClick={() => setFmeaState((prev: FMEAState) => ({ ...prev, [axis]: val }))}
                className={`
                  w-10 h-8 rounded text-sm font-medium tabular-nums transition-all duration-200
                  ${isSelected 
                    ? "bg-surface-2 text-ink shadow-[0_1px_3px_rgba(0,0,0,0.3)] border border-hairline-strong z-10" 
                    : "text-ink-subtle hover:text-ink hover:bg-surface-1 transparent border border-transparent"}
                `}
              >
                {val}
              </button>
            );
          })}
        </div>
      </div>
    );
  };

  return (
    <div className="w-full max-w-[800px] flex flex-col gap-8 animate-in fade-in duration-500">
      
      {/* Hidden file input */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,application/pdf"
        className="hidden"
        onChange={handleFileChange}
      />

      {/* ERROR TOAST */}
      {errorMsg && (
        <div className="fixed top-6 right-6 bg-[#3B1219] border border-[#EF4444]/30 shadow-lg px-4 py-3 rounded-lg flex items-center gap-3 z-50 animate-in slide-in-from-top-2 duration-300">
          <div className="w-5 h-5 rounded-full bg-[#EF4444]/20 flex items-center justify-center">
            <svg className="w-3 h-3 text-[#EF4444]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" /></svg>
          </div>
          <span className="text-sm font-medium text-[#FCA5A5]">{errorMsg}</span>
        </div>
      )}

      {/* 1. THE SMART DROPZONE */}
      <div 
        onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); }}
        onDrop={handleDrop}
        onClick={handleClick}
        className={`
          w-full h-[140px] rounded-xl border flex flex-col items-center justify-center transition-all duration-300
          ${dropState === "idle" ? "border-dashed border-hairline-strong bg-surface-1/50 hover:bg-surface-1 hover:border-primary/50 cursor-pointer" : ""}
          ${dropState === "extracting" ? "border-solid border-primary/50 bg-primary/5 cursor-wait" : ""}
          ${dropState === "success" ? "border-solid border-[#27a644]/50 bg-[#27a644]/5 cursor-pointer" : ""}
        `}
      >
        {dropState === "idle" && (
          <>
            <svg className="w-6 h-6 text-ink-subtle mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" /></svg>
            <p className="text-sm font-medium text-ink-subtle">Drop analytical protocol PDF here, or click to browse...</p>
          </>
        )}
        
        {dropState === "extracting" && (
          <>
            <div className="flex gap-1 mb-3">
              <div className="w-1.5 h-1.5 bg-primary rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></div>
              <div className="w-1.5 h-1.5 bg-primary rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></div>
              <div className="w-1.5 h-1.5 bg-primary rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></div>
            </div>
            <p className="text-sm font-medium font-mono text-primary animate-pulse">Extracting ICH Q14 parameters...</p>
          </>
        )}
        
        {dropState === "success" && (
          <>
            <div className="w-8 h-8 rounded-full bg-[#27a644]/20 flex items-center justify-center mb-2">
              <svg className="w-4 h-4 text-[#27a644]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M5 13l4 4L19 7" /></svg>
            </div>
            <p className="text-sm font-medium text-ink">{filename}</p>
            <p className="text-[11px] text-ink-tertiary mt-1">Click to replace file</p>
          </>
        )}
      </div>

      {/* 2. THE FMEA CONFIGURATION FORM */}
      <div className="bg-surface-1 border border-hairline rounded-xl p-6 shadow-sm">
        <h2 className="text-sm font-medium tracking-card-title text-ink-subtle mb-4">FMEA Risk Configuration</h2>
        
        <div className="flex flex-col">
          <SegmentControl axis="maturite" label="Maturité (Method Maturity)" description="1 = Compendial/Established, 2 = Adapted, 3 = Novel/First-time" />
          <SegmentControl axis="matrice" label="Matrice (Complexity)" description="1 = Simple API/Aqueous, 2 = Tablets/Capsules, 3 = Complex/Biofluids" />
          <SegmentControl axis="donnees" label="Données (Historical Data)" description="1 = Extensive (>3 batches), 2 = Limited (1-2 batches), 3 = None" />
          <SegmentControl axis="criticite" label="Criticité (Regulatory)" description="1 = In-process/R&D, 2 = Routine QC, 3 = Release/Submission" />
          <SegmentControl axis="risque" label="Risque Patient" description="1 = Low (Topical), 2 = Moderate (Oral solid), 3 = High (Injectable)" />
        </div>
      </div>

      {/* 3. ACTION FOOTER */}
      <div className="flex justify-end pt-4 border-t border-hairline mt-2">
        <button
          disabled={!isFormValid || isSubmitting}
          onClick={handleSubmit}
          className={`
            px-5 py-2.5 rounded-md text-sm font-medium transition-colors flex items-center gap-2
            ${isFormValid && !isSubmitting
              ? "bg-primary text-on-primary hover:bg-primary-hover shadow-sm" 
              : "bg-surface-2 text-ink-tertiary cursor-not-allowed border border-hairline"}
          `}
        >
          {isSubmitting && (
            <svg className="w-4 h-4 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
          )}
          Generate Validation Plan
        </button>
      </div>
    </div>
  );
}

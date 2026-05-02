"use client";

import React, { useState } from "react";
import LiveCopilot from "@/components/LiveCopilot";
import ValidationSetup from "@/components/ValidationSetup";
import ValidationReport from "@/components/ValidationReport";

export default function Home() {
  const [currentView, setCurrentView] = useState<"setup" | "copilot" | "report">("setup");
  const [sessionData, setSessionData] = useState<any>({ fmea: null, copilot: null });

  // ─── Lifted dropzone state (persists across tab switches) ───
  const [dropState, setDropState] = useState<"idle" | "extracting" | "success" | "error">("idle");
  const [uploadedFilename, setUploadedFilename] = useState("");
  const [drugName, setDrugName] = useState("");
  const [fmeaState, setFmeaState] = useState({
    maturite: null as number | null,
    matrice: null as number | null,
    donnees: null as number | null,
    criticite: null as number | null,
    risque: null as number | null,
  });

  return (
    <main className="flex h-screen w-full bg-canvas text-ink">
      {/* 1. FIXED LEFT SIDEBAR */}
      <aside className="w-[260px] flex-shrink-0 border-r border-hairline bg-canvas flex flex-col">
        {/* Workspace Dropdown Area */}
        <div className="h-[56px] border-b border-hairline flex items-center px-4 cursor-pointer hover:bg-surface-1 transition-colors">
          <div className="flex items-center gap-2 w-full">
            <div className="w-5 h-5 rounded-sm bg-primary flex items-center justify-center text-on-primary text-[10px] font-bold">
              B
            </div>
            <span className="font-medium text-sm">Biopharm QC Lab 2</span>
            <svg className="w-3 h-3 text-ink-subtle ml-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7" />
            </svg>
          </div>
        </div>

        {/* Navigation Links */}
        <nav className="flex-1 py-4 px-3 space-y-1">
          <div className="text-[13px] font-medium tracking-[0.4px] text-ink-subtle mb-2 px-2">WORKSPACE</div>
          
          <a 
            href="#" 
            onClick={(e) => { e.preventDefault(); setCurrentView("setup"); }}
            className={`flex items-center gap-2 py-[6px] rounded-md font-medium text-sm transition-colors ${
              currentView === "setup" 
                ? "bg-surface-1 text-ink border-l-[3px] border-primary pl-[9px] pr-2" 
                : "hover:bg-surface-1 text-ink-subtle hover:text-ink px-3"
            }`}
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
            New Protocol
          </a>
          
          <a 
            href="#" 
            onClick={(e) => { e.preventDefault(); setCurrentView("copilot"); }}
            className={`flex items-center gap-2 py-[6px] rounded-md font-medium text-sm transition-colors ${
              currentView === "copilot" 
                ? "bg-surface-1 text-ink border-l-[3px] border-primary pl-[9px] pr-2" 
                : "hover:bg-surface-1 text-ink-subtle hover:text-ink px-3"
            }`}
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
            Live Execution
          </a>

          <a 
            href="#" 
            onClick={(e) => { e.preventDefault(); setCurrentView("report"); }}
            className={`flex items-center gap-2 py-[6px] rounded-md font-medium text-sm transition-colors ${
              currentView === "report" 
                ? "bg-surface-1 text-ink border-l-[3px] border-primary pl-[9px] pr-2" 
                : "hover:bg-surface-1 text-ink-subtle hover:text-ink px-3"
            }`}
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
            Final Report
          </a>
          <a href="#" className="flex items-center gap-2 px-3 py-[6px] rounded-md hover:bg-surface-1 text-ink-subtle hover:text-ink transition-colors font-medium text-sm">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
            Equipment Health
          </a>
        </nav>
        
        {/* User Profile / Settings at Bottom */}
        <div className="p-4 border-t border-hairline">
          <div className="flex items-center gap-2 cursor-pointer group">
            <div className="w-6 h-6 rounded-full bg-surface-2 flex items-center justify-center text-xs">U</div>
            <span className="text-sm font-medium text-ink-subtle group-hover:text-ink transition-colors">User Settings</span>
          </div>
        </div>
      </aside>

      {/* 2. MAIN WORKSPACE */}
      <div className="flex-1 flex flex-col min-w-0">
        
        {/* Top Header */}
        <header className="h-[56px] border-b border-hairline bg-canvas flex items-center px-6 shrink-0">
          <div className="flex items-center gap-2 text-sm">
            <span className="text-ink-subtle hover:text-ink cursor-pointer transition-colors">Validations</span>
            <span className="text-ink-tertiary">/</span>
            <span className="text-ink font-medium">
              {currentView === "setup" ? "New Protocol" : currentView === "copilot" ? "Live Execution Copilot" : "Validation Analytics"}
            </span>
          </div>
          
          <div className="ml-4 px-2 py-0.5 rounded-full bg-surface-2 text-ink-muted text-[12px] flex items-center gap-1.5">
            {currentView === "setup" ? (
               <><div className="w-1.5 h-1.5 rounded-full bg-semantic-success"></div>System Online</>
            ) : currentView === "copilot" ? (
               <><div className="w-1.5 h-1.5 rounded-full bg-semantic-success animate-pulse"></div>Acquiring Telemetry</>
            ) : (
               <><div className="w-1.5 h-1.5 rounded-full bg-semantic-success"></div>Report Generated</>
            )}
          </div>
        </header>

        {/* Scrollable Content Area */}
        <div className="flex-1 overflow-auto p-8">
          
          {/* Main Title Area */}
          <div className={`mx-auto mb-10 ${currentView === "setup" ? "max-w-[1024px]" : "max-w-[1200px]"}`}>
            {currentView !== "report" && (
              <h1 className="text-[40px] font-semibold tracking-display-md leading-[1.15] mb-2 text-ink">
                {drugName || "New Validation Protocol"}
              </h1>
            )}
            {currentView !== "report" && (
              <p className="text-[18px] text-ink-subtle tracking-tight leading-[1.50] max-w-[600px]">
                {currentView === "setup" 
                  ? "Extracting documents, structuring matrices, and calculating Bayesian priors for the early-stopping Monte Carlo sequence."
                  : "Live analytical sequence injection tracking. The Bayesian engine calculates Monte Carlo pass probabilities in real-time."}
              </p>
            )}
          </div>

          <div className={`mx-auto flex justify-center ${currentView === "setup" ? "max-w-[1024px]" : "max-w-[1200px]"}`}>
            {currentView === "setup" && (
              <ValidationSetup 
                dropState={dropState}
                setDropState={setDropState}
                filename={uploadedFilename}
                setFilename={setUploadedFilename}
                drugName={drugName}
                setDrugName={setDrugName}
                fmeaState={fmeaState}
                setFmeaState={setFmeaState}
                onComplete={(data) => { 
                  console.log("🚀 SPARK — Navigating to Final Report with data:", data);
                  setSessionData((prev: any) => ({ ...prev, fmea: data })); 
                  setCurrentView("report"); 
                }} 
              />
            )}
            {currentView === "copilot" && (
              <LiveCopilot 
                onComplete={(data) => { 
                  setSessionData((prev: any) => ({ ...prev, copilot: data })); 
                  setCurrentView("report"); 
                }} 
              />
            )}
            {currentView === "report" && <ValidationReport data={sessionData} />}
          </div>

        </div>
      </div>
    </main>
  );
}

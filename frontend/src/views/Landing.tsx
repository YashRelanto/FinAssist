import React, { useState } from 'react';
import { TopNav } from '../components/TopNav';
import { AuthDialog } from '../components/AuthDialog';
import { useAppContext } from '../context/AppContext';
import { APP_NAME } from '../lib/utils';
import { BrandMark } from '../components/BrandMark';
import { FoundationScrollSection } from '../components/landing/FoundationScrollSection';
import { LandingHeroDashboard } from '../components/landing/LandingHeroDashboard';
import { ProductFeaturesSection } from '../components/landing/ProductFeaturesSection';
import { CustomerBasesSection } from '../components/landing/CustomerBasesSection';
import { ManifestoScrollSection } from '../components/landing/ManifestoScrollSection';
import { AIAssistantHighlight } from '../components/landing/AIAssistantHighlight';
import { LandingPreloader } from '../components/landing/LandingPreloader';

const TRUST_BRANDS = [
  'AI Assistant',
  'Designed for clarity',
  'Privacy First',
  'Smarter Planning',
  'Unified Financial View',
  'Precision Analytics',
];

export const Landing: React.FC = () => {
  const { user, setCurrentPage, authError, clearAuthError } = useAppContext();
  const [authOpen, setAuthOpen] = useState(false);
  const isAuthenticated = user.isAuthenticated;

  return (
    <div className="min-h-screen text-lumio-text selection:bg-lumio-black selection:text-white">
      <TopNav
        variant={isAuthenticated ? 'app' : 'landing'}
        onAuthClick={() => {
          clearAuthError();
          setAuthOpen(true);
        }}
      />
      {!isAuthenticated && (
        <>
          {authError && (
            <div className="fixed top-24 left-1/2 -translate-x-1/2 z-[90] max-w-md w-[calc(100%-2rem)] px-4 py-3 bg-error-container/90 border border-error/30 rounded-xl text-error text-sm font-semibold shadow-lg">
              {authError}
              <button
                type="button"
                onClick={clearAuthError}
                className="ml-3 underline text-xs"
              >
                Dismiss
              </button>
            </div>
          )}
          <AuthDialog open={authOpen} onClose={() => setAuthOpen(false)} />
        </>
      )}

      <main>
        <section className="pt-48 px-margin max-w-[1728px] mx-auto flex flex-col items-center text-center pb-32">
          <h1 className="font-hero text-6xl md:text-8xl lg:text-[100px] leading-[0.92] tracking-wide uppercase text-balance max-w-4xl mb-8">
            One Platform for every Financial Decision
          </h1>
          <p className="text-lg text-lumio-muted max-w-2xl mb-10 leading-relaxed">
            Turns scattered financial information into a single source of truth
          </p>
          <div className="w-full max-w-5xl bg-panel-bg overflow-hidden shadow-2xl relative z-10 rounded-[40px] aspect-[16/9] max-h-[500px] border border-lumio-line/20">
            <LandingHeroDashboard />
          </div>
        </section>

        <ProductFeaturesSection />

        <section className="py-16 px-margin border-t border-lumio-line/30 max-w-[1728px] mx-auto">
          <div className="marquee-container">
            <div className="animate-lumio-marquee flex gap-[100px] items-center text-lumio-muted">
              {[...TRUST_BRANDS, ...TRUST_BRANDS].map((brand, i) => (
                <span key={`${brand}-${i}`} className="text-xl font-semibold tracking-tight whitespace-nowrap">
                  {brand}
                </span>
              ))}
            </div>
          </div>
        </section>

        <FoundationScrollSection />

        <ManifestoScrollSection />

        <CustomerBasesSection />

        <AIAssistantHighlight />

        <section id="cta" className="py-32 px-margin">
          <div className="max-w-4xl mx-auto flex flex-col items-center text-center">
            <div className="flex justify-center mb-10">
              <BrandMark variant="light" nameClassName="text-base normal-case tracking-tight font-display font-bold" />
            </div>
            <h2 className="font-display text-4xl md:text-6xl font-bold tracking-tighter leading-[1.05] mb-10 text-balance">
              Experience the future of financial intelligence
            </h2>
            <div className="flex flex-col sm:flex-row gap-4">
              {isAuthenticated ? (
                <button
                  type="button"
                  onClick={() => setCurrentPage('dashboard')}
                  className="bg-lumio-black text-white font-label rounded-full px-8 py-3 text-[10px] font-bold uppercase tracking-wider hover:bg-lumio-text/80 transition-colors"
                >
                  Open Dashboard
                </button>
              ) : (
                <>
                  <button
                    type="button"
                    onClick={() => setAuthOpen(true)}
                    className="bg-lumio-black text-white font-label rounded-full px-8 py-3 text-[10px] font-bold uppercase tracking-wider hover:bg-lumio-text/80 transition-colors"
                  >
                    Get Started
                  </button>
                  <button
                    type="button"
                    onClick={() => setAuthOpen(true)}
                    className="border border-lumio-text/30 font-label rounded-full px-8 py-3 text-[10px] font-bold uppercase tracking-wider hover:bg-lumio-text hover:text-white transition-colors"
                  >
                    Sign In
                  </button>
                </>
              )}
            </div>
          </div>
        </section>
      </main>

      <footer className="bg-lumio-black text-white pt-20 pb-12 px-margin rounded-t-[64px]">
        <div className="max-w-[1728px] mx-auto grid grid-cols-1 md:grid-cols-4 gap-12 mb-16">
          <div>
            <div className="mb-6">
              <BrandMark variant="dark" showName nameClassName="text-page-bg/90" />
            </div>
            <p className="text-white/50 text-sm max-w-xs">
              The operating system for modern finance. Empowering focus through intelligent asset management.
            </p>
          </div>
          {[
            { title: 'Product', links: ['Dashboard', 'Analytics', `${APP_NAME} Assistant`, 'Forecasting'] },
            { title: 'Company', links: ['About', 'Careers', 'Contact'] },
            { title: 'Resources', links: ['Documentation', 'Support', 'Privacy'] },
          ].map((col) => (
            <div key={col.title}>
              <h4 className="font-label text-[10px] uppercase tracking-widest mb-4">{col.title}</h4>
              <ul className="space-y-3">
                {col.links.map((link) => (
                  <li key={link}>
                    <span className="text-sm text-white/60">{link}</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
        <div className="pt-8 border-t border-white/10 flex flex-col md:flex-row justify-between gap-4 text-[11px] text-white/40 font-label">
          <p>© {new Date().getFullYear()} {APP_NAME}. All rights reserved.</p>
          <div className="flex gap-6">
            <span>Privacy Policy</span>
            <span>Terms of Service</span>
          </div>
        </div>
      </footer>
    </div>
  );
};

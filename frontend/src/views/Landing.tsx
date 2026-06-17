import React, { useState } from 'react';
import { TopNav } from '../components/TopNav';
import { AuthDialog } from '../components/AuthDialog';
import { useAppContext } from '../context/AppContext';
import { APP_NAME } from '../lib/utils';
import { BrandMark } from '../components/BrandMark';
import { FoundationScrollSection } from '../components/landing/FoundationScrollSection';
import { LandingHeroDashboard } from '../components/landing/LandingHeroDashboard';

const HERO_IMAGE =
  'https://lh3.googleusercontent.com/aida-public/AB6AXuAcWbGUdACr36fX5hq-oT8ngiA2oYJGmnxAuMCv8IdYpfmCPhQFCgMjJVe8S1SNbcmYtXokWEjq7HXcuDPqsK66nAOCWDwwcFnAi7rLIiGgq0g4ciJ9HTaa_-y83MYXjI0tC86fE7SfguLA6iZM4nPo-IvPIuEsdJ8I8HhX_UpvxAj6oP-EDtty-0DvKpE8X0rOlIO9Xs6aMeYigq4zDwSC8lIPL8OkX7edi3UY4poLurpq-LSLK2Op14VLN44qL8TscvRN9LtcZDCo';

const TRUST_BRANDS = [
  'Designed for clarity',
  'Privacy First',
  'Smarter Planning',
  'Unified Financial View',
  'Precision Analytics',
];

const USE_CASES = [
  {
    title: 'Market Analysis',
    desc: 'Generate comprehensive reports aligned with portfolio strategy.',
    image:
      'https://lh3.googleusercontent.com/aida-public/AB6AXuBuMLs5Etr282ziHGQ97qSR_FW7o8KVbN5I0cxtVsoe9tuiC2VR1EuL3W2Eh6W_kPkQRsnk_bwnhy7JgNsf6Iyiq8Y41zzmb9AilMJJSTIDZlS68R9rf8ujHZQnABMMfFqSHo4VhFWv87RGdlvwD5Y8La_Tidtnc0XM8oI6I4st_LM9cZfHhP7TsziILGGRT--BMEEB5mEloXIVxfSJ3A1r6UC8PX9xxzAylxQ3sTBFdhyUX8M21v4z_JPwdXcUK-UTTYOg9V1zETjI',
  },
  {
    title: 'Risk Assessment',
    desc: 'Ensure compliance and stability across all investments.',
    image: HERO_IMAGE,
  },
  {
    title: 'Budget Planning',
    desc: 'Empower teams with up-to-date, structured spending data.',
    image:
      'https://lh3.googleusercontent.com/aida-public/AB6AXuAwKGdFgAHSj6Ezip4VTA15Faz_307SpXnRvVEdxj_KmdlUUgh-iR5Q_HBI-GZtIBCDOBXCtjGX3OTlydTQ8wIQOMqizGfOJ1pxT6JJpczWRgvmILVhew1LruibCBmM_UcWq2kCgX1dfOuIdVIo2DrdSGc8dTSaM5n2GG6VEIJN5kXZ55PXq8RdlcOvm7GZn4ANaYrE4o9f8hk0ES05NA9lu2awVwx1WP-5fd6y0I7pMeXmXDsJ6TXD60vmomEkeXG5OHXs-PbbuBox',
  },
  {
    title: 'AI Insights',
    desc: 'Codify your financial goals and get intelligent recommendations.',
    image:
      'https://lh3.googleusercontent.com/aida-public/AB6AXuBuMLs5Etr282ziHGQ97qSR_FW7o8KVbN5I0cxtVsoe9tuiC2VR1EuL3W2Eh6W_kPkQRsnk_bwnhy7JgNsf6Iyiq8Y41zzmb9AilMJJSTIDZlS68R9rf8ujHZQnABMMfFqSHo4VhFWv87RGdlvwD5Y8La_Tidtnc0XM8oI6I4st_LM9cZfHhP7TsziILGGRT--BMEEB5mEloXIVxfSJ3A1r6UC8PX9xxzAylxQ3sTBFdhyUX8M21v4z_JPwdXcUK-UTTYOg9V1zETjI',
  },
];

export const Landing: React.FC = () => {
  const { user, setCurrentPage } = useAppContext();
  const [authOpen, setAuthOpen] = useState(false);
  const isAuthenticated = user.isAuthenticated;

  return (
    <div className="min-h-screen text-lumio-text selection:bg-lumio-black selection:text-white">
      <TopNav
        variant={isAuthenticated ? 'app' : 'landing'}
        onAuthClick={() => setAuthOpen(true)}
      />
      {!isAuthenticated && <AuthDialog open={authOpen} onClose={() => setAuthOpen(false)} />}

      <main>
        <section className="pt-48 px-margin max-w-[1728px] mx-auto flex flex-col items-center text-center pb-32">
          <h1 className="font-display text-5xl md:text-7xl lg:text-[82px] leading-[1.05] tracking-tighter text-balance max-w-4xl mb-8">
            One Platform for every Financial Decision
          </h1>
          <p className="text-lg text-lumio-muted max-w-2xl mb-10 leading-relaxed">
            Turns scattered financial information into a single source of truth
          </p>
          <div className="w-full max-w-5xl bg-panel-bg overflow-hidden shadow-2xl relative z-10 rounded-[40px] aspect-[16/9] max-h-[500px] border border-lumio-line/20">
            <LandingHeroDashboard />
          </div>
        </section>

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

        <section id="manifesto" className="py-32 px-margin max-w-[1000px] mx-auto text-center">
          <h2 className="font-display text-3xl md:text-5xl leading-[1.1] tracking-tight text-balance font-light">
            As financial data expands across your life, the need for a singular source of truth has never been more
            critical. {APP_NAME} unifies your strategy.
          </h2>
        </section>

        <section className="py-24 px-margin max-w-[1728px] mx-auto">
          <h2 className="font-display text-3xl font-bold text-center mb-12">Built for every team.</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            {USE_CASES.map((item) => (
              <div
                key={item.title}
                className="relative h-[320px] rounded-[32px] p-8 flex flex-col justify-end overflow-hidden border border-lumio-line/20 group"
              >
                <img
                  alt={item.title}
                  className="absolute inset-0 w-full h-full object-cover transition-transform duration-500 group-hover:scale-105"
                  src={item.image}
                />
                <div className="absolute inset-0 bg-black/45" />
                <div className="relative z-10">
                  <h3 className="text-xl font-bold text-white mb-2">{item.title}</h3>
                  <p className="text-white/80 text-sm">{item.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </section>

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

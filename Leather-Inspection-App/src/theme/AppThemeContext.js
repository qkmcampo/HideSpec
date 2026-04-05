import React, { createContext, useContext, useMemo, useState } from 'react';

const darkTheme = {
  bg: '#0d1117',
  card: '#161b22',
  border: '#30363d',
  text: '#e6edf3',
  dim: '#8b949e',
  muted: '#484f58',
  accent: '#f0883e',
  good: '#3fb950',
  bad: '#f85149',
  blue: '#58a6ff',
  white: '#ffffff',
  liveOverlay: 'rgba(0,0,0,0.7)',
  feedBg: '#000000',
  goodSoft: 'rgba(63,185,80,0.08)',
  badSoft: 'rgba(248,81,73,0.08)',
  accentSoft: 'rgba(240,136,62,0.12)',
  accentSoftStrong: 'rgba(240,136,62,0.15)',
  accentSoftBorder: 'rgba(240,136,62,0.3)',
  goodSoftBorder: 'rgba(63,185,80,0.18)',
  badSoftBorder: 'rgba(248,81,73,0.18)',
  subtle: 'rgba(255,255,255,0.05)',
  subtle2: 'rgba(255,255,255,0.03)',
  dividerSoft: 'rgba(48,54,61,0.5)',
  barBg: '#21262d',
};

const lightTheme = {
  bg: '#f6f8fa',
  card: '#ffffff',
  border: '#d0d7de',
  text: '#24292f',
  dim: '#57606a',
  muted: '#6e7781',
  accent: '#f0883e',
  good: '#1a7f37',
  bad: '#cf222e',
  blue: '#0969da',
  white: '#ffffff',
  liveOverlay: 'rgba(255,255,255,0.9)',
  feedBg: '#000000',
  goodSoft: 'rgba(26,127,55,0.08)',
  badSoft: 'rgba(207,34,46,0.08)',
  accentSoft: 'rgba(240,136,62,0.12)',
  accentSoftStrong: 'rgba(240,136,62,0.16)',
  accentSoftBorder: 'rgba(240,136,62,0.35)',
  goodSoftBorder: 'rgba(26,127,55,0.18)',
  badSoftBorder: 'rgba(207,34,46,0.18)',
  subtle: 'rgba(0,0,0,0.05)',
  subtle2: 'rgba(0,0,0,0.03)',
  dividerSoft: 'rgba(208,215,222,0.8)',
  barBg: '#d8dee4',
};

const AppThemeContext = createContext({
  themeMode: 'dark',
  theme: darkTheme,
  toggleTheme: () => {},
});

export function AppThemeProvider({ children }) {
  const [themeMode, setThemeMode] = useState('dark');

  const value = useMemo(() => {
    const theme = themeMode === 'dark' ? darkTheme : lightTheme;
    return {
      themeMode,
      theme,
      toggleTheme: () => {
        setThemeMode((prev) => (prev === 'dark' ? 'light' : 'dark'));
      },
    };
  }, [themeMode]);

  return (
    <AppThemeContext.Provider value={value}>
      {children}
    </AppThemeContext.Provider>
  );
}

export function useAppTheme() {
  return useContext(AppThemeContext);
}
import React, { useEffect, useState } from 'react';
import { inspectionService as api, subscribeToInspections as subscribe, API_BASE_URL as apiBase, STREAM_URL as streamBase, VIDEO_FEED_URL as videoFeedUrl } from './services/inspectionService';

const periods = [['today', 'Today'], ['week', '7 Days'], ['month', '30 Days'], ['all', 'All Time']];
const formatDefectType = (type) => String(type || 'unknown').replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());

function Card({ title, children }) {
  return <section className="card"><h2>{title}</h2>{children}</section>;
}

function Metric({ label, value, tone = '' }) {
  return <div className="metric"><span>{label}</span><strong className={tone}>{value ?? 0}</strong></div>;
}

function Monitor({ data, refresh }) {
  const session = data.status?.session || {};
  const machine = data.stream?.machine || {};
  const stats = data.stream?.stats || {};
  const live = data.feedReady;
  const currentResult = live ? (stats.grade || machine.current_result || 'SCANNING') : 'OFFLINE';
  const currentHint = live ? 'Camera feed is active and ready for inspection.' : 'Waiting for camera feed.';

  return (
    <main className="page dashboard">
      <section className="inspection-layout">
        <div className="monitor-panel">
          <Card title="Live Leather Inspection">
            <span className={`pill ${live ? 'good' : 'bad'}`}>{live ? 'LIVE' : 'OFFLINE'}</span>
            <div className="feed feed-hero">
              <img
                src={videoFeedUrl}
                alt="Live leather inspection stream"
                onLoad={data.setFeedReady}
                onError={data.setFeedDown}
              />
            </div>
            <p className="result">{live ? 'SCANNING' : 'OFFLINE'}</p>
          </Card>
        </div>

        <aside className="right-panel">
          <Card title="Session Summary">
            <div className="metrics session-metrics">
              <Metric label="Total inspected" value={session.total_inspected} />
              <Metric label="Passed" value={session.good_count} tone="good" />
              <Metric label="Failed" value={session.bad_count} tone="bad" />
              <Metric label="Defect rate" value={`${session.defect_rate || 0}%`} tone="accent" />
            </div>
          </Card>

          <Card title="Recent Inspections">
            <div className="table compact-table">
              <table>
                <thead><tr><th>Hide ID</th><th>Result</th><th>Defects</th><th>Recorded</th></tr></thead>
                <tbody>
                  {data.history.length ? data.history.map((item) => (
                    <tr key={item.id || item.created_at}>
                      <td>{item.hide_id}</td>
                      <td className={item.classification === 'Good' ? 'good' : 'bad'}>{item.classification}</td>
                      <td>{item.total_defects || 0}</td>
                      <td>{item.created_at}</td>
                    </tr>
                  )) : <tr><td colSpan="4">No inspection history yet.</td></tr>}
                </tbody>
              </table>
            </div>
          </Card>

          <Card title="Current Inspection">
            <div className={`current-result ${String(currentResult).includes('BAD') ? 'bad-result' : 'good-result'}`}>
              <div className="current-status">{live ? 'LIVE MONITOR' : 'OFFLINE'}</div>
              <strong>{currentResult || 'WAITING FOR LEATHER'}</strong>
              <span>{currentHint}</span>
            </div>
            {data.latest ? (
              <div className="latest current-details">
                <strong>{data.latest.hide_id}</strong>
                <span>{data.latest.classification} ? {data.latest.total_defects || 0} defects</span>
                <small>{data.latest.created_at || '?'}</small>
              </div>
            ) : (
              <p className="empty-state">The latest completed inspection will appear here.</p>
            )}
          </Card>

          <Card title="Controls">
            <button onClick={refresh}>Refresh data</button>
            <button className="danger" onClick={data.reset}>Reset history</button>
            <p className="connection">API: {apiBase}<br />Stream: {streamBase}</p>
          </Card>
        </aside>
      </section>
    </main>
  );
}

function Analytics({ data, period, setPeriod }) {
  const summary = data.summary || {};
  const defects = data.defects || [];
  const timeline = data.timeline || [];
  const quality = data.quality || {};
  const area = data.area || {};
  const maximum = Math.max(1, ...timeline.flatMap((item) => [item.good || 0, item.bad || 0]));
  const total = defects.reduce((sum, item) => sum + item.count, 0);

  return (
    <main className="page">
      <div className="periods">
        {periods.map(([key, label]) => (
          <button className={period === key ? 'active' : ''} key={key} onClick={() => setPeriod(key)}>{label}</button>
        ))}
      </div>
      <Card title="Overview">
        <div className="metrics">
          <Metric label="Inspected" value={summary.total_inspections} />
          <Metric label="Passed" value={summary.good_count} tone="good" />
          <Metric label="Failed" value={summary.bad_count} tone="bad" />
          <Metric label="Pass rate" value={`${summary.pass_rate || 0}%`} tone="good" />
          <Metric label="Fail rate" value={`${summary.defect_rate || 0}%`} tone="bad" />
          <Metric label="Avg. defects" value={summary.avg_defects_per_hide} tone="accent" />
        </div>
      </Card>
      <Card title="Quality Index">
        <strong className="quality">{summary.pass_rate || 0}%</strong>
        <div className="progress"><i style={{ width: `${summary.pass_rate || 0}%` }} /></div>
      </Card>
      <Card title="Threshold Check">
        <div className="metrics">
          <Metric label="Good by threshold" value={quality.good} tone="good" />
          <Metric label="Bad by threshold" value={quality.bad} tone="bad" />
          <Metric label="Threshold" value={`${quality.threshold_percent || 20}%`} tone="accent" />
          <Metric label="Avg defect area" value={`${area.avg_percent || 0}%`} tone="accent" />
        </div>
      </Card>
      {timeline.length > 0 && (
        <Card title="Inspection Timeline">
          <div className="chart">
            {timeline.map((item, index) => (
              <div className="chart-item" key={`${item.time_label}-${index}`}>
                <div>
                  <i className="good-bar" style={{ height: `${(item.good || 0) / maximum * 100}%` }} />
                  <i className="bad-bar" style={{ height: `${(item.bad || 0) / maximum * 100}%` }} />
                </div>
                <small>{item.time_label}</small>
              </div>
            ))}
          </div>
        </Card>
      )}
      <Card title="Defect Distribution">
        {defects.length ? defects.map((item, index) => {
          const share = total ? item.count / total * 100 : 0;
          return (
            <div className="defect" key={item.type}>
              <span>{formatDefectType(item.type)}</span>
              <div><i style={{ width: `${share}%`, background: ['#f0883e', '#f85149', '#58a6ff', '#3fb950'][index % 4] }} /></div>
              <strong>{item.count} ({share.toFixed(1)}%)</strong>
            </div>
          );
        }) : <p>No defects recorded for this period.</p>}
      </Card>
    </main>
  );
}

function About() {
  return (
    <main className="page">
      <Card title="HideSpec">
        <p className="eyebrow">CAPSTONE DESIGN PROJECT</p>
        <h1>Deep Learning-Based Defect Classification for Leather Hides Inspection</h1>
        <p>with Segregation System · Technological Institute of the Philippines · Team 10</p>
      </Card>
      <Card title="System Architecture">
        <ol>
          <li>Feeding and transport</li>
          <li>Camera inspection and YOLOv8 defect detection</li>
          <li>Encoder-synchronised marking</li>
          <li>Automated sorting and segregation</li>
        </ol>
      </Card>
      <Card title="Technology Stack">
        <p>Raspberry Pi 5 · Arduino Uno · YOLOv8n · Flask + SQLite · React + Vite</p>
      </Card>
    </main>
  );
}

export default function App() {
  const [tab, setTab] = useState('monitor');
  const [dark, setDark] = useState(false);
  const [period, setPeriod] = useState('all');
  const [monitor, setMonitor] = useState({ status: {}, latest: null, history: [], feedReady: false });
  const [analytics, setAnalytics] = useState({ loading: false, summary: {}, defects: [], timeline: [], quality: {}, area: {} });

  const refreshAnalytics = async () => {
    setAnalytics((current) => ({ ...current, loading: true }));
    try {
      const [summary, defects, timeline, quality, area] = await Promise.all([
        api.analytics(period),
        api.defects(period),
        api.timeline(period),
        api.quality(period),
        api.defectArea(period),
      ]);
      setAnalytics({
        loading: false,
        summary,
        defects: defects.defects || [],
        timeline: timeline.timeline || [],
        quality,
        area,
      });
    } catch {
      setAnalytics({ loading: false, summary: {}, defects: [], timeline: [], quality: {}, area: {} });
    }
  };

  const refreshMonitor = async () => {
    const [status, latest, history] = await Promise.all([api.status(), api.latest(), api.history()]);
    setMonitor((current) => ({
      ...current,
      status,
      latest,
      history: history.inspections || [],
      reset: async () => {
        if (window.confirm('Reset all inspection history?')) {
          await api.reset();
          refreshMonitor();
        }
      },
    }));
  };

  useEffect(() => {
    refreshMonitor();
    const unsubscribe = subscribe(refreshMonitor);
    const timer = setInterval(refreshMonitor, 2000);
    return () => {
      unsubscribe();
      clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    if (tab === 'analytics') {
      refreshAnalytics();
      const timer = setInterval(refreshAnalytics, 2000);
      return () => clearInterval(timer);
    }
  }, [tab, period]);

  const setFeedReady = () => setMonitor((current) => ({ ...current, feedReady: true }));
  const setFeedDown = () => setMonitor((current) => ({ ...current, feedReady: false }));
  const page = tab === 'monitor'
    ? <Monitor data={{ ...monitor, setFeedReady, setFeedDown }} refresh={refreshMonitor} />
    : tab === 'analytics'
      ? <Analytics data={analytics} period={period} setPeriod={setPeriod} />
      : <About />;

  return (
    <div className={dark ? 'app dark' : 'app'}>
      <header>
        <b>HIDESPEC</b>
        <nav>{[['monitor', 'Monitor'], ['analytics', 'Analytics'], ['about', 'About']].map(([key, label]) => <button key={key} className={tab === key ? 'selected' : ''} onClick={() => setTab(key)}>{label}</button>)}</nav>
        <aside><button onClick={() => setDark(!dark)}>{dark ? 'Light' : 'Dark'}</button></aside>
      </header>
      {page}
    </div>
  );
}



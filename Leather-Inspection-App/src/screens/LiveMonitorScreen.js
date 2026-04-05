import React, { useState, useEffect, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  RefreshControl,
  Image,
  ActivityIndicator,
  TouchableOpacity,
  Animated,
  Platform,
} from 'react-native';
import StatusBadge from '../components/StatusBadge';
import DefectCard from '../components/DefectCard';
import { VIDEO_FEED_URL, STREAM_URL, SNAPSHOT_URL } from '../config/api';
import {
  connectWebSocket,
  disconnectWebSocket,
  getLatestInspection,
  getInspections,
  getSystemStatus,
} from '../services/inspectionService';

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
  liveOverlay: 'rgba(0,0,0,0.7)',
  feedBg: '#000',
  goodSoft: 'rgba(63,185,80,0.06)',
  goodSoftBorder: 'rgba(63,185,80,0.15)',
  badSoft: 'rgba(248,81,73,0.08)',
  accentSoft: 'rgba(240,136,62,0.1)',
  accentSoftStrong: 'rgba(240,136,62,0.15)',
  accentSoftBorder: 'rgba(240,136,62,0.3)',
  whiteSoftBorder: 'rgba(255,255,255,0.04)',
  dividerSoft: 'rgba(48,54,61,0.5)',
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
  liveOverlay: 'rgba(255,255,255,0.88)',
  feedBg: '#000',
  goodSoft: 'rgba(26,127,55,0.08)',
  goodSoftBorder: 'rgba(26,127,55,0.18)',
  badSoft: 'rgba(207,34,46,0.08)',
  accentSoft: 'rgba(240,136,62,0.12)',
  accentSoftStrong: 'rgba(240,136,62,0.16)',
  accentSoftBorder: 'rgba(240,136,62,0.35)',
  whiteSoftBorder: 'rgba(0,0,0,0.06)',
  dividerSoft: 'rgba(208,215,222,0.8)',
};

function FadeSlideIn({ delay = 0, direction = 'up', children, style }) {
  const opacity = useRef(new Animated.Value(0)).current;
  const translate = useRef(
    new Animated.Value(
      direction === 'up'
        ? 40
        : direction === 'down'
        ? -40
        : direction === 'left'
        ? 40
        : -40
    )
  ).current;

  useEffect(() => {
    Animated.sequence([
      Animated.delay(delay),
      Animated.parallel([
        Animated.timing(opacity, {
          toValue: 1,
          duration: 500,
          useNativeDriver: true,
        }),
        Animated.spring(translate, {
          toValue: 0,
          friction: 6,
          tension: 40,
          useNativeDriver: true,
        }),
      ]),
    ]).start();
  }, [delay, opacity, translate]);

  const transform =
    direction === 'up' || direction === 'down'
      ? [{ translateY: translate }]
      : [{ translateX: translate }];

  return (
    <Animated.View style={[{ opacity, transform }, style]}>
      {children}
    </Animated.View>
  );
}

function PulseDot({ connected, C, styles }) {
  const pulse = useRef(new Animated.Value(1)).current;

  useEffect(() => {
    Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, {
          toValue: 1.8,
          duration: 800,
          useNativeDriver: true,
        }),
        Animated.timing(pulse, {
          toValue: 1,
          duration: 800,
          useNativeDriver: true,
        }),
      ])
    ).start();
  }, [pulse]);

  return (
    <View style={styles.pulseContainer}>
      <Animated.View
        style={[
          styles.pulseRing,
          {
            backgroundColor: connected
              ? 'rgba(63,185,80,0.2)'
              : 'rgba(248,81,73,0.2)',
            transform: [{ scale: pulse }],
          },
        ]}
      />
      <View
        style={[
          styles.pulseDot,
          { backgroundColor: connected ? C.good : C.bad },
        ]}
      />
    </View>
  );
}

function LiveIndicator({ styles, C }) {
  const blink = useRef(new Animated.Value(1)).current;

  useEffect(() => {
    Animated.loop(
      Animated.sequence([
        Animated.timing(blink, {
          toValue: 0.2,
          duration: 500,
          useNativeDriver: true,
        }),
        Animated.timing(blink, {
          toValue: 1,
          duration: 500,
          useNativeDriver: true,
        }),
      ])
    ).start();
  }, [blink]);

  return (
    <View style={styles.liveIndicator}>
      <Animated.View style={[styles.liveDot, { opacity: blink, backgroundColor: C.bad }]} />
      <Text style={[styles.liveText, { color: C.bad }]}>LIVE</Text>
    </View>
  );
}

function WebStream({ width, styles }) {
  return (
    <View style={[styles.webFeedWrap, { maxWidth: width }]}>
      <img
        src={VIDEO_FEED_URL}
        alt="Live Detection Feed"
        style={styles.webFeedImage}
      />
    </View>
  );
}

function NativeSnapshot({ height, styles }) {
  return (
    <Image
      source={{ uri: SNAPSHOT_URL }}
      style={[styles.feedImage, { height }]}
      resizeMode="contain"
    />
  );
}

export default function LiveMonitorScreen() {
  const [themeMode, setThemeMode] = useState('dark');
  const C = themeMode === 'dark' ? darkTheme : lightTheme;
  const styles = getStyles(C);

  const [connected, setConnected] = useState(false);
  const [latestResult, setLatestResult] = useState(null);
  const [recentHistory, setRecentHistory] = useState([]);
  const [systemStatus, setSystemStatus] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [showLiveFeed, setShowLiveFeed] = useState(true);
  const [streamInfo, setStreamInfo] = useState(null);
  const [feedSize, setFeedSize] = useState('medium');

  const FEED_HEIGHTS = {
    small: 180,
    medium: 280,
    large: 400,
    full: 550,
  };

  const FEED_WIDTHS = {
    small: 520,
    medium: 700,
    large: 860,
    full: 1100,
  };

  const cardScale = useRef(new Animated.Value(1)).current;

  const animateNewInspection = () => {
    Animated.sequence([
      Animated.spring(cardScale, {
        toValue: 1.02,
        friction: 3,
        useNativeDriver: true,
      }),
      Animated.spring(cardScale, {
        toValue: 1,
        friction: 5,
        useNativeDriver: true,
      }),
    ]).start();
  };

  const fetchStreamStatus = async () => {
    try {
      const res = await fetch(`${STREAM_URL}/api/stream/status`);
      if (res.ok) {
        const data = await res.json();
        setStreamInfo(data);
      }
    } catch (e) {
      console.log('Stream status unavailable:', e?.message || e);
    }
  };

  async function loadData() {
    try {
      const [status, latest, history] = await Promise.all([
        getSystemStatus(),
        getLatestInspection(),
        getInspections(20),
      ]);

      if (status) setSystemStatus(status);
      if (latest) setLatestResult(latest);
      if (history?.inspections) setRecentHistory(history.inspections);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  useEffect(() => {
    loadData();
    fetchStreamStatus();

    connectWebSocket({
      onConnect: () => setConnected(true),
      onDisconnect: () => setConnected(false),
      onNewInspection: (data) => {
        setLatestResult(data);
        setRecentHistory((prev) => [data, ...prev].slice(0, 20));
        animateNewInspection();
      },
      onStatusUpdate: (data) => {
        setSystemStatus((prev) => ({ ...prev, session: data }));
      },
    });

    const interval = setInterval(loadData, 10000);
    const streamInterval = setInterval(fetchStreamStatus, 10000);

    return () => {
      clearInterval(interval);
      clearInterval(streamInterval);
      disconnectWebSocket();
    };
  }, []);

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color={C.accent} />
        <Text style={styles.loadingText}>ESTABLISHING CONNECTION</Text>
        <Text style={styles.loadingSub}>Connecting to inspection system...</Text>
      </View>
    );
  }

  return (
    <ScrollView
      style={styles.container}
      refreshControl={
        <RefreshControl
          refreshing={refreshing}
          onRefresh={() => {
            setRefreshing(true);
            loadData();
            fetchStreamStatus();
          }}
          tintColor={C.accent}
          colors={[C.accent]}
        />
      }
    >
      <FadeSlideIn delay={0} direction="down">
        <View style={styles.statusBar}>
          <View style={styles.statusLeft}>
            <PulseDot connected={connected} C={C} styles={styles} />
            <View style={{ marginLeft: 16 }}>
              <Text
                style={[
                  styles.statusLabel,
                  { color: connected ? C.good : C.bad },
                ]}
              >
                {connected ? 'SYSTEM ONLINE' : 'RECONNECTING'}
              </Text>
              <Text style={styles.statusSub}>
                {systemStatus?.system?.model || 'YOLOv8n'} ·{' '}
                {systemStatus?.system?.platform || 'Raspberry Pi 5'}
              </Text>
            </View>
          </View>

          <View style={styles.headerActions}>
            <TouchableOpacity
              style={styles.themeBtn}
              onPress={() => setThemeMode((prev) => (prev === 'dark' ? 'light' : 'dark'))}
            >
              <Text style={styles.themeBtnText}>
                {themeMode === 'dark' ? 'LIGHT' : 'DARK'}
              </Text>
            </TouchableOpacity>

            {systemStatus?.session && (
              <View style={styles.statusRight}>
                <Text style={styles.statusCount}>
                  {systemStatus.session.total_inspected || 0}
                </Text>
                <Text style={styles.statusCountLabel}>TOTAL</Text>
              </View>
            )}
          </View>
        </View>
      </FadeSlideIn>

      {systemStatus?.session && (
        <FadeSlideIn delay={100} direction="up">
          <View style={styles.quickStats}>
            <View
              style={[
                styles.quickStatItem,
                { borderRightWidth: 1, borderRightColor: C.border },
              ]}
            >
              <Text style={[styles.quickStatValue, { color: C.good }]}>
                {systemStatus.session.good_count || 0}
              </Text>
              <Text style={styles.quickStatLabel}>PASSED</Text>
            </View>
            <View
              style={[
                styles.quickStatItem,
                { borderRightWidth: 1, borderRightColor: C.border },
              ]}
            >
              <Text style={[styles.quickStatValue, { color: C.bad }]}>
                {systemStatus.session.bad_count || 0}
              </Text>
              <Text style={styles.quickStatLabel}>FAILED</Text>
            </View>
            <View style={styles.quickStatItem}>
              <Text style={[styles.quickStatValue, { color: C.accent }]}>
                {systemStatus.session.defect_rate || 0}%
              </Text>
              <Text style={styles.quickStatLabel}>DEFECT RATE</Text>
            </View>
          </View>
        </FadeSlideIn>
      )}

      <FadeSlideIn delay={150} direction="up">
        <View style={styles.section}>
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionDot}>●</Text>
            <Text style={styles.sectionTitle}>LIVE DETECTION FEED</Text>
            <TouchableOpacity
              style={[
                styles.toggleBtn,
                showLiveFeed && styles.toggleBtnActive,
              ]}
              onPress={() => setShowLiveFeed(!showLiveFeed)}
            >
              <Text
                style={[
                  styles.toggleText,
                  showLiveFeed && styles.toggleTextActive,
                ]}
              >
                {showLiveFeed ? 'HIDE' : 'SHOW'}
              </Text>
            </TouchableOpacity>
          </View>

          {showLiveFeed && (
            <View style={styles.feedCard}>
              <LiveIndicator styles={styles} C={C} />

              <View style={styles.sizeControls}>
                {['small', 'medium', 'large', 'full'].map((size) => (
                  <TouchableOpacity
                    key={`size-${size}`}
                    style={[
                      styles.sizeBtn,
                      feedSize === size && styles.sizeBtnActive,
                    ]}
                    onPress={() => setFeedSize(size)}
                  >
                    <Text
                      style={[
                        styles.sizeBtnText,
                        feedSize === size && styles.sizeBtnTextActive,
                      ]}
                    >
                      {size === 'small'
                        ? 'S'
                        : size === 'medium'
                        ? 'M'
                        : size === 'large'
                        ? 'L'
                        : 'XL'}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>

              {Platform.OS === 'web' ? (
                <WebStream width={FEED_WIDTHS[feedSize]} styles={styles} />
              ) : (
                <NativeSnapshot height={FEED_HEIGHTS[feedSize]} styles={styles} />
              )}

              <View style={styles.feedInfoBar}>
                <Text style={styles.feedInfoText}>
                  Pi Camera Module 3 · YOLOv8n ·{' '}
                  {streamInfo?.resolution || '640x480'}
                </Text>

                {streamInfo?.detections && (
                  <View style={styles.feedDetectionBadge}>
                    <Text style={styles.feedDetectionText}>
                      {streamInfo.detections.length} defect
                      {streamInfo.detections.length !== 1 ? 's' : ''}
                    </Text>
                  </View>
                )}
              </View>

              {streamInfo?.detections && streamInfo.detections.length > 0 && (
                <View style={styles.feedDetections}>
                  {streamInfo.detections.map((d, i) => (
                    <View key={`live-defect-${i}`} style={styles.feedDefectItem}>
                      <View
                        style={[
                          styles.feedDefectDot,
                          {
                            backgroundColor:
                              d.type === 'color_defect'
                                ? C.accent
                                : d.type === 'hole'
                                ? C.bad
                                : C.blue,
                          },
                        ]}
                      />
                      <Text style={styles.feedDefectType}>{d.label}</Text>
                      <Text style={styles.feedDefectConf}>
                        {Math.round(d.confidence * 100)}%
                      </Text>
                    </View>
                  ))}
                </View>
              )}
            </View>
          )}
        </View>
      </FadeSlideIn>

      <FadeSlideIn delay={200} direction="up">
        <View style={styles.section}>
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionDot}>●</Text>
            <Text style={styles.sectionTitle}>LATEST INSPECTION</Text>
          </View>

          {latestResult ? (
            <Animated.View
              style={[styles.latestCard, { transform: [{ scale: cardScale }] }]}
            >
              <View style={styles.latestHeader}>
                <View>
                  <Text style={styles.hideId}>{latestResult.hide_id}</Text>
                  <Text style={styles.timestamp}>
                    {latestResult.created_at
                      ? new Date(latestResult.created_at).toLocaleTimeString([], {
                          hour: '2-digit',
                          minute: '2-digit',
                          second: '2-digit',
                        })
                      : '—'}
                  </Text>
                </View>
                <StatusBadge
                  classification={latestResult.classification}
                  size="large"
                />
              </View>

              <View
                style={[
                  styles.resultBar,
                  {
                    backgroundColor:
                      latestResult.classification === 'Good'
                        ? C.goodSoft
                        : C.badSoft,
                  },
                ]}
              >
                <Text
                  style={[
                    styles.resultBarText,
                    {
                      color:
                        latestResult.classification === 'Good'
                          ? C.good
                          : C.bad,
                    },
                  ]}
                >
                  {latestResult.classification === 'Good'
                    ? '▲  HIDE APPROVED — ROUTE TO GOOD BIN'
                    : '▼  HIDE REJECTED — ROUTE TO DEFECT BIN'}
                </Text>
              </View>

              <View style={styles.defectsHeader}>
                <Text style={styles.defectsTitle}>DETECTED DEFECTS</Text>
                <View style={styles.defectCountBadge}>
                  <Text style={styles.defectCountText}>
                    {latestResult.total_defects || 0}
                  </Text>
                </View>
              </View>

              {latestResult.defects && latestResult.defects.length > 0 ? (
                latestResult.defects.map((defect, index) => (
                  <FadeSlideIn
                    key={`defect-${index}-${defect.type}`}
                    delay={300 + index * 100}
                    direction="left"
                  >
                    <DefectCard defect={defect} />
                  </FadeSlideIn>
                ))
              ) : (
                <View style={styles.noDefectsBox}>
                  <Text style={styles.noDefectsIcon}>✓</Text>
                  <Text style={styles.noDefectsText}>No defects detected</Text>
                  <Text style={styles.noDefectsSub}>
                    Surface inspection passed all checks
                  </Text>
                </View>
              )}
            </Animated.View>
          ) : (
            <View style={styles.emptyCard}>
              <View style={styles.emptyPulse}>
                <Text style={styles.emptyIcon}>◎</Text>
              </View>
              <Text style={styles.emptyTitle}>AWAITING INSPECTION</Text>
              <Text style={styles.emptySub}>
                Feed a leather hide through the machine{'\n'}to begin quality
                analysis
              </Text>
            </View>
          )}
        </View>
      </FadeSlideIn>

      <FadeSlideIn delay={400} direction="up">
        <View style={styles.section}>
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionDot}>●</Text>
            <Text style={styles.sectionTitle}>INSPECTION LOG</Text>
            <Text style={styles.sectionCount}>{recentHistory.length} records</Text>
          </View>

          {recentHistory.length > 0 ? (
            recentHistory.map((item, index) => (
              <FadeSlideIn
                key={`history-${index}-${item.hide_id}`}
                delay={500 + index * 50}
                direction="right"
              >
                <TouchableOpacity style={styles.historyItem} activeOpacity={0.6}>
                  <View
                    style={[
                      styles.historyIndicator,
                      {
                        backgroundColor:
                          item.classification === 'Good' ? C.good : C.bad,
                      },
                    ]}
                  />
                  <View style={styles.historyContent}>
                    <View style={styles.historyTop}>
                      <Text style={styles.historyHideId}>{item.hide_id}</Text>
                      <StatusBadge
                        classification={item.classification}
                        size="small"
                      />
                    </View>
                    <View style={styles.historyBottom}>
                      <Text style={styles.historyTime}>
                        {item.created_at
                          ? new Date(item.created_at).toLocaleTimeString([], {
                              hour: '2-digit',
                              minute: '2-digit',
                            })
                          : '—'}
                      </Text>
                      <Text style={styles.historyDefects}>
                        {item.total_defects || 0} defect
                        {(item.total_defects || 0) !== 1 ? 's' : ''}
                      </Text>
                    </View>
                  </View>
                </TouchableOpacity>
              </FadeSlideIn>
            ))
          ) : (
            <Text style={styles.noHistory}>No inspection records</Text>
          )}
        </View>
      </FadeSlideIn>

      <View style={{ height: 40 }} />
    </ScrollView>
  );
}

const getStyles = (C) =>
  StyleSheet.create({
    container: { flex: 1, backgroundColor: C.bg },
    center: {
      flex: 1,
      justifyContent: 'center',
      alignItems: 'center',
      backgroundColor: C.bg,
    },
    loadingText: {
      marginTop: 16,
      fontSize: 12,
      color: C.accent,
      fontWeight: '800',
      letterSpacing: 2,
    },
    loadingSub: { marginTop: 4, fontSize: 12, color: C.muted },

    pulseContainer: {
      width: 24,
      height: 24,
      justifyContent: 'center',
      alignItems: 'center',
    },
    pulseRing: {
      position: 'absolute',
      width: 24,
      height: 24,
      borderRadius: 12,
    },
    pulseDot: { width: 10, height: 10, borderRadius: 5 },

    statusBar: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'center',
      paddingHorizontal: 16,
      paddingVertical: 14,
      backgroundColor: C.card,
      borderBottomWidth: 1,
      borderBottomColor: C.border,
    },
    statusLeft: { flexDirection: 'row', alignItems: 'center', flex: 1 },
    headerActions: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 10,
    },
    statusLabel: { fontSize: 11, fontWeight: '800', letterSpacing: 1.5 },
    statusSub: { fontSize: 10, color: C.muted, marginTop: 2, letterSpacing: 0.3 },
    statusRight: { alignItems: 'center', minWidth: 56 },
    statusCount: { fontSize: 22, fontWeight: '900', color: C.text },
    statusCountLabel: {
      fontSize: 8,
      color: C.muted,
      fontWeight: '700',
      letterSpacing: 1.5,
    },

    themeBtn: {
      paddingHorizontal: 10,
      paddingVertical: 6,
      borderRadius: 6,
      borderWidth: 1,
      borderColor: C.border,
      backgroundColor: C.bg,
    },
    themeBtnText: {
      fontSize: 9,
      fontWeight: '800',
      color: C.text,
      letterSpacing: 1,
    },

    quickStats: {
      flexDirection: 'row',
      backgroundColor: C.card,
      borderBottomWidth: 1,
      borderBottomColor: C.border,
    },
    quickStatItem: { flex: 1, alignItems: 'center', paddingVertical: 12 },
    quickStatValue: { fontSize: 20, fontWeight: '900' },
    quickStatLabel: {
      fontSize: 8,
      color: C.muted,
      fontWeight: '700',
      letterSpacing: 1.5,
      marginTop: 2,
    },

    section: { paddingHorizontal: 16, marginTop: 20 },
    sectionHeader: { flexDirection: 'row', alignItems: 'center', marginBottom: 12 },
    sectionDot: { color: C.accent, fontSize: 8, marginRight: 8 },
    sectionTitle: {
      fontSize: 11,
      fontWeight: '800',
      color: C.dim,
      letterSpacing: 1.5,
      flex: 1,
    },
    sectionCount: { fontSize: 10, color: C.muted },

    toggleBtn: {
      paddingHorizontal: 10,
      paddingVertical: 4,
      borderRadius: 4,
      borderWidth: 1,
      borderColor: C.border,
      backgroundColor: C.bg,
    },
    toggleBtnActive: {
      borderColor: C.accent,
      backgroundColor: C.accentSoft,
    },
    toggleText: {
      fontSize: 9,
      fontWeight: '800',
      color: C.muted,
      letterSpacing: 1,
    },
    toggleTextActive: { color: C.accent },

    feedCard: {
      backgroundColor: C.card,
      borderRadius: 12,
      overflow: 'hidden',
      borderWidth: 1,
      borderColor: C.border,
      position: 'relative',
    },

    feedImage: {
      width: '100%',
      backgroundColor: C.feedBg,
    },

    webFeedWrap: {
      width: '100%',
      aspectRatio: 4 / 3,
      alignSelf: 'center',
      backgroundColor: C.feedBg,
    },

    webFeedImage: {
      width: '100%',
      height: '100%',
      objectFit: 'contain',
      display: 'block',
      backgroundColor: C.feedBg,
    },

    sizeControls: {
      position: 'absolute',
      top: 10,
      right: 10,
      zIndex: 10,
      flexDirection: 'row',
      gap: 4,
      backgroundColor: C.liveOverlay,
      borderRadius: 6,
      padding: 3,
    },
    sizeBtn: {
      width: 28,
      height: 24,
      borderRadius: 4,
      justifyContent: 'center',
      alignItems: 'center',
    },
    sizeBtnActive: { backgroundColor: C.accent },
    sizeBtnText: {
      fontSize: 9,
      fontWeight: '800',
      color: C.muted,
      letterSpacing: 0.5,
    },
    sizeBtnTextActive: { color: '#fff' },

    liveIndicator: {
      position: 'absolute',
      top: 10,
      left: 10,
      zIndex: 10,
      flexDirection: 'row',
      alignItems: 'center',
      backgroundColor: C.liveOverlay,
      borderRadius: 4,
      paddingHorizontal: 8,
      paddingVertical: 4,
    },
    liveDot: {
      width: 8,
      height: 8,
      borderRadius: 4,
      marginRight: 6,
    },
    liveText: {
      fontSize: 10,
      fontWeight: '900',
      letterSpacing: 1.5,
    },

    feedInfoBar: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'center',
      paddingHorizontal: 12,
      paddingVertical: 8,
      borderTopWidth: 1,
      borderTopColor: C.border,
    },
    feedInfoText: { fontSize: 9, color: C.muted, letterSpacing: 0.3 },
    feedDetectionBadge: {
      backgroundColor: C.accentSoftStrong,
      borderRadius: 8,
      paddingHorizontal: 8,
      paddingVertical: 3,
      borderWidth: 1,
      borderColor: C.accentSoftBorder,
    },
    feedDetectionText: { fontSize: 9, fontWeight: '800', color: C.accent },
    feedDetections: {
      paddingHorizontal: 12,
      paddingBottom: 10,
      borderTopWidth: 1,
      borderTopColor: C.dividerSoft,
    },
    feedDefectItem: {
      flexDirection: 'row',
      alignItems: 'center',
      paddingVertical: 4,
    },
    feedDefectDot: { width: 6, height: 6, borderRadius: 3, marginRight: 8 },
    feedDefectType: { fontSize: 11, color: C.dim, flex: 1 },
    feedDefectConf: { fontSize: 11, color: C.muted, fontFamily: 'monospace' },

    latestCard: {
      backgroundColor: C.card,
      borderRadius: 12,
      padding: 16,
      borderWidth: 1,
      borderColor: C.border,
      overflow: 'hidden',
    },
    latestHeader: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'flex-start',
      marginBottom: 14,
    },
    hideId: { fontSize: 22, fontWeight: '900', color: C.text, letterSpacing: -0.3 },
    timestamp: { fontSize: 12, color: C.muted, marginTop: 3, fontFamily: 'monospace' },
    resultBar: {
      borderRadius: 8,
      padding: 10,
      marginBottom: 14,
      borderWidth: 1,
      borderColor: C.whiteSoftBorder,
    },
    resultBarText: {
      fontSize: 10,
      fontWeight: '800',
      letterSpacing: 1,
      textAlign: 'center',
    },

    defectsHeader: {
      flexDirection: 'row',
      alignItems: 'center',
      marginBottom: 10,
      marginTop: 4,
    },
    defectsTitle: {
      fontSize: 10,
      fontWeight: '800',
      color: C.dim,
      letterSpacing: 1.5,
      flex: 1,
    },
    defectCountBadge: {
      backgroundColor: C.accentSoftStrong,
      borderRadius: 10,
      paddingHorizontal: 10,
      paddingVertical: 3,
      borderWidth: 1,
      borderColor: C.accentSoftBorder,
    },
    defectCountText: { fontSize: 11, fontWeight: '800', color: C.accent },

    noDefectsBox: {
      backgroundColor: C.goodSoft,
      borderRadius: 10,
      padding: 20,
      alignItems: 'center',
      borderWidth: 1,
      borderColor: C.goodSoftBorder,
    },
    noDefectsIcon: { fontSize: 28, color: C.good, marginBottom: 6 },
    noDefectsText: { fontSize: 13, color: C.good, fontWeight: '700' },
    noDefectsSub: { fontSize: 11, color: C.muted, marginTop: 2 },

    emptyCard: {
      backgroundColor: C.card,
      borderRadius: 12,
      padding: 50,
      alignItems: 'center',
      borderWidth: 1,
      borderColor: C.border,
    },
    emptyPulse: {
      width: 60,
      height: 60,
      borderRadius: 30,
      backgroundColor: C.accentSoft,
      justifyContent: 'center',
      alignItems: 'center',
      marginBottom: 16,
      borderWidth: 1,
      borderColor: C.accentSoftBorder,
    },
    emptyIcon: { fontSize: 28, color: C.accent },
    emptyTitle: {
      fontSize: 12,
      fontWeight: '800',
      color: C.dim,
      letterSpacing: 2,
    },
    emptySub: {
      fontSize: 12,
      color: C.muted,
      textAlign: 'center',
      marginTop: 8,
      lineHeight: 18,
    },

    historyItem: {
      backgroundColor: C.card,
      borderRadius: 10,
      marginBottom: 6,
      borderWidth: 1,
      borderColor: C.border,
      flexDirection: 'row',
      overflow: 'hidden',
    },
    historyIndicator: { width: 3 },
    historyContent: { flex: 1, padding: 12 },
    historyTop: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'center',
    },
    historyHideId: { fontSize: 14, fontWeight: '700', color: C.text },
    historyBottom: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      marginTop: 6,
    },
    historyTime: { fontSize: 11, color: C.muted, fontFamily: 'monospace' },
    historyDefects: { fontSize: 11, color: C.dim },
    noHistory: {
      fontSize: 12,
      color: C.muted,
      textAlign: 'center',
      paddingVertical: 30,
    },
  });
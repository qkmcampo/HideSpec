import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  RefreshControl,
  TouchableOpacity,
  Image,
  ActivityIndicator,
  Alert,
} from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import { useAppTheme } from '../theme/AppThemeContext';

const API_BASE_URL = 'http://192.168.1.100:5000';
const STREAM_BASE_URL = 'http://192.168.1.100:5001';

const STATUS_URL = `${API_BASE_URL}/api/status`;
const LATEST_URL = `${API_BASE_URL}/api/inspections/latest`;
const HISTORY_URL = `${API_BASE_URL}/api/inspections?limit=10`;
const RESET_URL = `${API_BASE_URL}/api/history/reset`;

const STREAM_STATUS_URL = `${STREAM_BASE_URL}/api/stream/status`;
const LIVE_FEED_URL = `${STREAM_BASE_URL}/video_feed`;

export default function LiveMonitorScreen() {
  const { theme: C } = useAppTheme();

  const [refreshing, setRefreshing] = useState(false);
  const [loading, setLoading] = useState(true);

  const [systemStatus, setSystemStatus] = useState(null);
  const [streamStatus, setStreamStatus] = useState(null);
  const [latestResult, setLatestResult] = useState(null);
  const [recentHistory, setRecentHistory] = useState([]);

  const [error, setError] = useState(null);

  const session = useMemo(
    () =>
      systemStatus?.session || {
        total_inspected: 0,
        good_count: 0,
        bad_count: 0,
        defect_rate: 0,
      },
    [systemStatus]
  );

  const inspectionEvent = streamStatus?.inspection_event || {
    active: false,
    current_hide_id: null,
    collected_defects: [],
  };

  const currentDetections = streamStatus?.detections || [];
  const performance = streamStatus?.performance || {};

  const cardStyle = useMemo(
    () => [
      styles.card,
      {
        backgroundColor: C.card,
        borderColor: C.border,
        shadowColor: '#000',
      },
    ],
    [C]
  );

  const chipStyle = useMemo(
    () => ({
      backgroundColor: C.bg,
      borderColor: C.border,
    }),
    [C]
  );

  const fetchJson = async (url) => {
    const res = await fetch(url);
    if (res.status === 404) {
      return null;
    }
    if (!res.ok) {
      throw new Error(`Request failed: ${res.status}`);
    }
    return res.json();
  };

  const loadMonitorData = async ({ silent = false } = {}) => {
    try {
      if (!silent) {
        setError(null);
      }

      const [statusData, streamData, latestData, historyData] = await Promise.all([
        fetchJson(STATUS_URL),
        fetchJson(STREAM_STATUS_URL),
        fetchJson(LATEST_URL),
        fetchJson(HISTORY_URL),
      ]);

      setSystemStatus(statusData || null);
      setStreamStatus(streamData || null);
      setLatestResult(latestData || null);
      setRecentHistory(historyData?.inspections || []);
      setError(null);
    } catch (err) {
      setError(err.message || 'Failed to load monitor data');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    loadMonitorData();

    const interval = setInterval(() => {
      loadMonitorData({ silent: true });
    }, 2500);

    return () => clearInterval(interval);
  }, []);

  useFocusEffect(
    useCallback(() => {
      loadMonitorData({ silent: true });
    }, [])
  );

  const onRefresh = () => {
    setRefreshing(true);
    loadMonitorData();
  };

  const handleReset = (deleteCaptures) => {
    Alert.alert(
      deleteCaptures ? 'Reset History + Captures' : 'Reset History Only',
      deleteCaptures
        ? 'Delete all inspection history and captured images?'
        : 'Delete all inspection history?',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Reset',
          style: 'destructive',
          onPress: async () => {
            try {
              const res = await fetch(RESET_URL, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ delete_captures: deleteCaptures }),
              });

              const data = await res.json();

              if (!res.ok) {
                throw new Error(data?.error || 'Reset failed');
              }

              Alert.alert('Success', data?.message || 'History reset successfully');
              setLatestResult(null);
              setRecentHistory([]);
              loadMonitorData();
            } catch (err) {
              Alert.alert('Reset Failed', err.message || 'Could not reset history');
            }
          },
        },
      ]
    );
  };

  const getClassificationTone = (classification) => {
    if (classification === 'Good') {
      return {
        bg: C.goodSoft || 'rgba(46,160,67,0.12)',
        border: C.goodSoftBorder || 'rgba(46,160,67,0.25)',
        text: C.good || '#2ea043',
        label: 'GOOD',
      };
    }

    return {
      bg: C.badSoft || 'rgba(248,81,73,0.12)',
      border: C.badSoftBorder || 'rgba(248,81,73,0.25)',
      text: C.bad || '#f85149',
      label: 'BAD',
    };
  };

  const renderStatCard = (label, value, accent) => (
    <View
      style={[
        styles.statCard,
        {
          backgroundColor: C.bg,
          borderColor: C.border,
        },
      ]}
    >
      <Text style={[styles.statLabel, { color: C.muted }]}>{label}</Text>
      <Text style={[styles.statValue, { color: accent || C.text }]}>{value}</Text>
    </View>
  );

  const renderDefectPill = (defect, index) => (
    <View
      key={`${defect.type}-${index}`}
      style={[
        styles.defectPill,
        {
          backgroundColor: C.bg,
          borderColor: C.border,
        },
      ]}
    >
      <Text style={[styles.defectType, { color: C.text }]}>
        {defect.type || defect.label || 'unknown'}
      </Text>
      {typeof defect.confidence === 'number' ? (
        <Text style={[styles.defectConfidence, { color: C.muted }]}>
          {(defect.confidence * 100).toFixed(1)}%
        </Text>
      ) : null}
    </View>
  );

  if (loading) {
    return (
      <View style={[styles.loadingWrap, { backgroundColor: C.bg }]}>
        <ActivityIndicator size="large" color={C.accent} />
        <Text style={[styles.loadingText, { color: C.muted }]}>Loading monitor...</Text>
      </View>
    );
  }

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: C.bg }}
      contentContainerStyle={styles.container}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
      showsVerticalScrollIndicator={false}
    >
      <View style={cardStyle}>
        <View style={styles.sectionHeader}>
          <Text style={[styles.sectionTitle, { color: C.text }]}>Live Feed</Text>
          <View
            style={[
              styles.liveBadge,
              {
                backgroundColor: streamStatus?.status === 'running'
                  ? (C.goodSoft || 'rgba(46,160,67,0.12)')
                  : (C.badSoft || 'rgba(248,81,73,0.12)'),
                borderColor: streamStatus?.status === 'running'
                  ? (C.goodSoftBorder || 'rgba(46,160,67,0.25)')
                  : (C.badSoftBorder || 'rgba(248,81,73,0.25)'),
              },
            ]}
          >
            <Text
              style={[
                styles.liveBadgeText,
                { color: streamStatus?.status === 'running' ? (C.good || '#2ea043') : (C.bad || '#f85149') },
              ]}
            >
              {streamStatus?.status === 'running' ? 'LIVE' : 'OFFLINE'}
            </Text>
          </View>
        </View>

        <View style={[styles.videoWrap, { backgroundColor: C.bg, borderColor: C.border }]}>
          <Image
            source={{ uri: `${LIVE_FEED_URL}?t=${Date.now()}` }}
            style={styles.video}
            resizeMode="cover"
          />
        </View>

        <View style={styles.metaRow}>
          <View style={[styles.metaChip, chipStyle]}>
            <Text style={[styles.metaLabel, { color: C.muted }]}>Resolution</Text>
            <Text style={[styles.metaValue, { color: C.text }]}>
              {streamStatus?.resolution || '--'}
            </Text>
          </View>

          <View style={[styles.metaChip, chipStyle]}>
            <Text style={[styles.metaLabel, { color: C.muted }]}>FPS</Text>
            <Text style={[styles.metaValue, { color: C.text }]}>
              {performance.actual_stream_fps ?? '--'}
            </Text>
          </View>

          <View style={[styles.metaChip, chipStyle]}>
            <Text style={[styles.metaLabel, { color: C.muted }]}>Inference</Text>
            <Text style={[styles.metaValue, { color: C.text }]}>
              {performance.last_inference_ms != null ? `${performance.last_inference_ms} ms` : '--'}
            </Text>
          </View>
        </View>
      </View>

      <View style={cardStyle}>
        <Text style={[styles.sectionTitle, { color: C.text }]}>Session Summary</Text>
        <View style={styles.statsGrid}>
          {renderStatCard('Total Inspected', session.total_inspected, C.text)}
          {renderStatCard('Good Count', session.good_count, C.good || '#2ea043')}
          {renderStatCard('Bad Count', session.bad_count, C.bad || '#f85149')}
          {renderStatCard('Defect Rate', `${session.defect_rate}%`, C.accent)}
        </View>
      </View>

      <View style={cardStyle}>
        <Text style={[styles.sectionTitle, { color: C.text }]}>Inspection Event</Text>

        <View
          style={[
            styles.eventBanner,
            {
              backgroundColor: inspectionEvent.active
                ? (C.accentSoft || 'rgba(88,166,255,0.10)')
                : C.bg,
              borderColor: inspectionEvent.active
                ? (C.accentSoftBorder || 'rgba(88,166,255,0.25)')
                : C.border,
            },
          ]}
        >
          <Text style={[styles.eventState, { color: inspectionEvent.active ? C.accent : C.muted }]}>
            {inspectionEvent.active ? 'ACTIVE HIDE EVENT' : 'NO ACTIVE HIDE EVENT'}
          </Text>
          <Text style={[styles.eventSubtext, { color: C.text }]}>
            Hide ID: {inspectionEvent.current_hide_id || '—'}
          </Text>
        </View>

        <Text style={[styles.subheading, { color: C.text }]}>Collected Defects</Text>
        <View style={styles.pillWrap}>
          {inspectionEvent.collected_defects?.length ? (
            inspectionEvent.collected_defects.map(renderDefectPill)
          ) : (
            <Text style={[styles.emptyText, { color: C.muted }]}>No collected defects yet.</Text>
          )}
        </View>

        <Text style={[styles.subheading, { color: C.text }]}>Current Frame Detections</Text>
        <View style={styles.pillWrap}>
          {currentDetections?.length ? (
            currentDetections.map(renderDefectPill)
          ) : (
            <Text style={[styles.emptyText, { color: C.muted }]}>No live detections right now.</Text>
          )}
        </View>
      </View>

      <View style={cardStyle}>
        <Text style={[styles.sectionTitle, { color: C.text }]}>Latest Inspection</Text>

        {!latestResult ? (
          <Text style={[styles.emptyText, { color: C.muted }]}>
            No inspection has been recorded yet.
          </Text>
        ) : (
          <>
            <View
              style={[
                styles.resultBanner,
                {
                  backgroundColor: getClassificationTone(latestResult.classification).bg,
                  borderColor: getClassificationTone(latestResult.classification).border,
                },
              ]}
            >
              <Text
                style={[
                  styles.resultBadge,
                  { color: getClassificationTone(latestResult.classification).text },
                ]}
              >
                {getClassificationTone(latestResult.classification).label}
              </Text>
              <Text style={[styles.resultHideId, { color: C.text }]}>
                {latestResult.hide_id}
              </Text>
            </View>

            <View style={styles.latestMetaRow}>
              <Text style={[styles.latestMetaText, { color: C.muted }]}>
                Total Defects: <Text style={{ color: C.text }}>{latestResult.total_defects ?? 0}</Text>
              </Text>
              <Text style={[styles.latestMetaText, { color: C.muted }]}>
                Created: <Text style={{ color: C.text }}>{latestResult.created_at || '--'}</Text>
              </Text>
            </View>

            <View style={styles.pillWrap}>
              {latestResult.defects?.length ? (
                latestResult.defects.map(renderDefectPill)
              ) : (
                <Text style={[styles.emptyText, { color: C.muted }]}>
                  This inspection was marked Good with no saved defects.
                </Text>
              )}
            </View>
          </>
        )}
      </View>

      <View style={cardStyle}>
        <Text style={[styles.sectionTitle, { color: C.text }]}>Recent History</Text>

        {!recentHistory.length ? (
          <Text style={[styles.emptyText, { color: C.muted }]}>No recent inspection history yet.</Text>
        ) : (
          recentHistory.map((item, index) => {
            const tone = getClassificationTone(item.classification);

            return (
              <View
                key={`${item.hide_id}-${index}`}
                style={[
                  styles.historyItem,
                  {
                    backgroundColor: C.bg,
                    borderColor: C.border,
                  },
                ]}
              >
                <View style={styles.historyTopRow}>
                  <Text style={[styles.historyHideId, { color: C.text }]}>{item.hide_id}</Text>
                  <View
                    style={[
                      styles.historyBadge,
                      {
                        backgroundColor: tone.bg,
                        borderColor: tone.border,
                      },
                    ]}
                  >
                    <Text style={[styles.historyBadgeText, { color: tone.text }]}>
                      {item.classification}
                    </Text>
                  </View>
                </View>

                <Text style={[styles.historyMeta, { color: C.muted }]}>
                  Defects: {item.total_defects ?? 0}
                </Text>
                <Text style={[styles.historyMeta, { color: C.muted }]}>
                  {item.created_at || '--'}
                </Text>

                <View style={styles.pillWrap}>
                  {item.defects?.length ? (
                    item.defects.map(renderDefectPill)
                  ) : (
                    <Text style={[styles.emptyTextSmall, { color: C.muted }]}>No saved defects.</Text>
                  )}
                </View>
              </View>
            );
          })
        )}
      </View>

      <View style={cardStyle}>
        <Text style={[styles.sectionTitle, { color: C.text }]}>Actions</Text>

        <View style={styles.actionRow}>
          <TouchableOpacity
            style={[
              styles.actionButton,
              {
                backgroundColor: C.bg,
                borderColor: C.border,
              },
            ]}
            onPress={() => loadMonitorData()}
          >
            <Text style={[styles.actionButtonText, { color: C.text }]}>Refresh Now</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[
              styles.actionButton,
              {
                backgroundColor: C.badSoft || 'rgba(248,81,73,0.10)',
                borderColor: C.badSoftBorder || 'rgba(248,81,73,0.20)',
              },
            ]}
            onPress={() => handleReset(false)}
          >
            <Text style={[styles.actionButtonText, { color: C.bad || '#f85149' }]}>
              Reset History
            </Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[
              styles.actionButton,
              {
                backgroundColor: C.badSoft || 'rgba(248,81,73,0.10)',
                borderColor: C.badSoftBorder || 'rgba(248,81,73,0.20)',
              },
            ]}
            onPress={() => handleReset(true)}
          >
            <Text style={[styles.actionButtonText, { color: C.bad || '#f85149' }]}>
              Reset + Captures
            </Text>
          </TouchableOpacity>
        </View>

        {error ? (
          <Text style={[styles.errorText, { color: C.bad || '#f85149' }]}>
            {error}
          </Text>
        ) : null}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    padding: 14,
    paddingBottom: 30,
    gap: 14,
  },
  loadingWrap: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  loadingText: {
    marginTop: 12,
    fontSize: 14,
    fontWeight: '600',
  },
  card: {
    borderWidth: 1,
    borderRadius: 18,
    padding: 14,
    marginBottom: 14,
  },
  sectionHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: '800',
    letterSpacing: 0.4,
    marginBottom: 12,
  },
  liveBadge: {
    borderWidth: 1,
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 5,
  },
  liveBadgeText: {
    fontSize: 11,
    fontWeight: '800',
    letterSpacing: 1,
  },
  videoWrap: {
    borderWidth: 1,
    borderRadius: 16,
    overflow: 'hidden',
  },
  video: {
    width: '100%',
    aspectRatio: 4 / 3,
  },
  metaRow: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 12,
    flexWrap: 'wrap',
  },
  metaChip: {
    borderWidth: 1,
    borderRadius: 12,
    paddingHorizontal: 10,
    paddingVertical: 8,
    minWidth: 92,
  },
  metaLabel: {
    fontSize: 10,
    fontWeight: '700',
    textTransform: 'uppercase',
    letterSpacing: 0.8,
    marginBottom: 3,
  },
  metaValue: {
    fontSize: 13,
    fontWeight: '700',
  },
  statsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
  },
  statCard: {
    width: '47.5%',
    borderWidth: 1,
    borderRadius: 14,
    padding: 12,
  },
  statLabel: {
    fontSize: 11,
    fontWeight: '700',
    textTransform: 'uppercase',
    letterSpacing: 0.8,
    marginBottom: 6,
  },
  statValue: {
    fontSize: 22,
    fontWeight: '900',
  },
  eventBanner: {
    borderWidth: 1,
    borderRadius: 14,
    padding: 12,
    marginBottom: 12,
  },
  eventState: {
    fontSize: 13,
    fontWeight: '900',
    letterSpacing: 0.8,
  },
  eventSubtext: {
    marginTop: 6,
    fontSize: 13,
    fontWeight: '600',
  },
  subheading: {
    fontSize: 13,
    fontWeight: '800',
    marginTop: 8,
    marginBottom: 8,
    letterSpacing: 0.3,
  },
  pillWrap: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  defectPill: {
    borderWidth: 1,
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 7,
    marginBottom: 4,
  },
  defectType: {
    fontSize: 12,
    fontWeight: '800',
  },
  defectConfidence: {
    fontSize: 10,
    fontWeight: '600',
    marginTop: 2,
  },
  emptyText: {
    fontSize: 13,
    fontWeight: '600',
    marginBottom: 4,
  },
  emptyTextSmall: {
    fontSize: 12,
    fontWeight: '500',
  },
  resultBanner: {
    borderWidth: 1,
    borderRadius: 14,
    padding: 12,
    marginBottom: 12,
  },
  resultBadge: {
    fontSize: 12,
    fontWeight: '900',
    letterSpacing: 1,
    marginBottom: 6,
  },
  resultHideId: {
    fontSize: 15,
    fontWeight: '800',
  },
  latestMetaRow: {
    marginBottom: 10,
    gap: 4,
  },
  latestMetaText: {
    fontSize: 12,
    fontWeight: '600',
  },
  historyItem: {
    borderWidth: 1,
    borderRadius: 14,
    padding: 12,
    marginBottom: 10,
  },
  historyTopRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  historyHideId: {
    fontSize: 14,
    fontWeight: '800',
    flex: 1,
    marginRight: 8,
  },
  historyBadge: {
    borderWidth: 1,
    borderRadius: 999,
    paddingHorizontal: 9,
    paddingVertical: 5,
  },
  historyBadgeText: {
    fontSize: 11,
    fontWeight: '900',
    letterSpacing: 0.8,
  },
  historyMeta: {
    fontSize: 12,
    fontWeight: '600',
    marginTop: 4,
    marginBottom: 2,
  },
  actionRow: {
    gap: 10,
  },
  actionButton: {
    borderWidth: 1,
    borderRadius: 14,
    paddingVertical: 12,
    paddingHorizontal: 14,
    alignItems: 'center',
  },
  actionButtonText: {
    fontSize: 13,
    fontWeight: '800',
    letterSpacing: 0.4,
  },
  errorText: {
    marginTop: 12,
    fontSize: 12,
    fontWeight: '700',
  },
});
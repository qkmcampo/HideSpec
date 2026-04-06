import React, { useCallback, useEffect, useMemo, useRef, useState, memo } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  RefreshControl,
  TouchableOpacity,
  ActivityIndicator,
  Alert,
  useWindowDimensions,
  Platform,
} from 'react-native';
import { WebView } from 'react-native-webview';
import { useFocusEffect } from '@react-navigation/native';
import { useAppTheme } from '../theme/AppThemeContext';
import {
  getSystemStatus,
  getLatestInspection,
  getInspections,
  getStreamStatus,
  resetHistory,
  connectWebSocket,
  disconnectWebSocket,
} from '../services/inspectionService';
import { VIDEO_FEED_URL } from '../config/api';

const StreamSurface = memo(function StreamSurface({ borderColor }) {
  const html = `
    <!DOCTYPE html>
    <html>
      <head>
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
        <style>
          html, body {
            margin: 0;
            padding: 0;
            width: 100%;
            height: 100%;
            background: #000;
            overflow: hidden;
          }
          .wrap {
            width: 100%;
            height: 100%;
            background: #000;
            overflow: hidden;
          }
          img {
            width: 100%;
            height: 100%;
            object-fit: cover;
            display: block;
            background: #000;
          }
        </style>
      </head>
      <body>
        <div class="wrap">
          <img src="${VIDEO_FEED_URL}" alt="HideSpec Live Stream" />
        </div>
      </body>
    </html>
  `;

  if (Platform.OS === 'web') {
    return (
      <View style={[styles.videoWrap, { borderColor, backgroundColor: '#000' }]}>
        <img
          src={VIDEO_FEED_URL}
          alt="HideSpec Live Stream"
          style={{
            width: '100%',
            height: '100%',
            objectFit: 'cover',
            display: 'block',
            backgroundColor: '#000',
          }}
        />
      </View>
    );
  }

  return (
    <View style={[styles.videoWrap, { borderColor, backgroundColor: '#000' }]}>
      <WebView
        originWhitelist={['*']}
        source={{ html }}
        style={styles.webview}
        scrollEnabled={false}
        bounces={false}
        javaScriptEnabled
        domStorageEnabled
        allowsInlineMediaPlayback
        mediaPlaybackRequiresUserAction={false}
        setSupportMultipleWindows={false}
      />
    </View>
  );
});

export default function LiveMonitorScreen() {
  const { theme: C } = useAppTheme();
  const { width } = useWindowDimensions();

  const [refreshing, setRefreshing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [systemStatus, setSystemStatus] = useState(null);
  const [streamStatus, setStreamStatus] = useState(null);
  const [latestResult, setLatestResult] = useState(null);
  const [recentHistory, setRecentHistory] = useState([]);
  const [error, setError] = useState(null);

  const pollRef = useRef(null);

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

  const machine = streamStatus?.machine || {
    arduino_connected: false,
    leather_present: false,
    servo_busy: false,
    bad_triggered: false,
    consecutive_bad_frames: 0,
    missing_frames: 0,
    max_defects_seen: 0,
    current_defect_count: 0,
    current_result: 'WAITING FOR LEATHER',
    last_command_sent: null,
    last_result: null,
    last_result_time: null,
  };

  const inspectionEvent = streamStatus?.inspection_event || {
    active: false,
    current_hide_id: null,
    collected_defects: [],
  };

  const currentDetections = streamStatus?.detections || [];

  const isStreamOnline = streamStatus?.status === 'running';
  const isArduinoOnline = machine?.arduino_connected === true;
  const isBackendOnline = systemStatus?.status === 'online';

  const cardStyle = useMemo(
    () => [
      styles.card,
      {
        backgroundColor: C.card,
        borderColor: C.border,
      },
    ],
    [C]
  );

  const contentMaxWidth = Math.min(width - 24, 1180);
  const feedMaxWidth = Math.min(width - 56, 760);

  const liveStatusText = useMemo(() => {
    if (machine.servo_busy) return 'BAD DETECTED | Servo active';
    if (machine.leather_present) {
      return `INSPECTING | defects=${machine.current_defect_count ?? 0} | max=${machine.max_defects_seen ?? 0}`;
    }
    return 'WAITING FOR LEATHER';
  }, [machine]);

  const loadMonitorData = useCallback(async ({ silent = false } = {}) => {
    try {
      if (!silent) setError(null);

      const [statusData, latestData, historyData, streamData] = await Promise.all([
        getSystemStatus(),
        getLatestInspection(),
        getInspections(10),
        getStreamStatus(),
      ]);

      setSystemStatus(statusData || null);
      setLatestResult(latestData || null);
      setRecentHistory(historyData?.inspections || []);
      setStreamStatus(streamData || null);
    } catch (err) {
      setError(err.message || 'Failed to load monitor data');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadMonitorData();

    const socket = connectWebSocket({
      onConnectedMessage: (data) => {
        if (data?.session) {
          setSystemStatus((prev) => ({
            ...(prev || {}),
            status: prev?.status || 'online',
            message: prev?.message || 'HideSpec API server running',
            system: prev?.system || {
              model: 'YOLOv8n',
              platform: 'Raspberry Pi 5',
              camera: 'Pi Camera Module 3',
            },
            analytics: prev?.analytics || { defects_by_type: {} },
            session: data.session,
          }));
        }
      },
      onNewInspection: (data) => {
        if (data) {
          setLatestResult(data);
          setRecentHistory((prev) =>
            [data, ...prev.filter((item) => item.id !== data.id)].slice(0, 10)
          );
        }
      },
      onStatusUpdate: (data) => {
        if (data) {
          setSystemStatus((prev) => ({
            ...(prev || {}),
            status: prev?.status || 'online',
            message: prev?.message || 'HideSpec API server running',
            system: prev?.system || {
              model: 'YOLOv8n',
              platform: 'Raspberry Pi 5',
              camera: 'Pi Camera Module 3',
            },
            analytics: prev?.analytics || { defects_by_type: {} },
            session: data,
          }));
        }
      },
    });

    pollRef.current = setInterval(() => {
      loadMonitorData({ silent: true });
    }, 2000);

    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
      if (socket) disconnectWebSocket();
    };
  }, [loadMonitorData]);

  useFocusEffect(
    useCallback(() => {
      loadMonitorData({ silent: true });
    }, [loadMonitorData])
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
              const data = await resetHistory(deleteCaptures);
              Alert.alert('Success', data?.message || 'History reset successfully');
              setLatestResult(null);
              setRecentHistory([]);
              loadMonitorData({ silent: true });
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
    <View style={[styles.statCard, { backgroundColor: C.bg, borderColor: C.border }]}>
      <Text style={[styles.statLabel, { color: C.muted }]}>{label}</Text>
      <Text style={[styles.statValue, { color: accent || C.text }]}>{value}</Text>
    </View>
  );

  const renderDefectPill = (defect, index) => (
    <View
      key={`${defect.type || defect.label || 'unknown'}-${index}`}
      style={[styles.defectPill, { backgroundColor: C.bg, borderColor: C.border }]}
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

  const renderMachineRow = (label, value, accent) => (
    <View style={[styles.machineRow, { backgroundColor: C.bg, borderColor: C.border }]}>
      <Text style={[styles.machineLabel, { color: C.muted }]}>{label}</Text>
      <Text style={[styles.machineValue, { color: accent || C.text }]}>{value}</Text>
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
      <View style={[styles.contentWrap, { maxWidth: contentMaxWidth }]}>
        <View style={[cardStyle, { backgroundColor: '#000' }]}>
          <View style={styles.sectionHeader}>
            <Text style={[styles.sectionTitle, { color: C.text }]}>Live Feed</Text>
            <View
              style={[
                styles.liveBadge,
                {
                  backgroundColor: isStreamOnline
                    ? C.goodSoft || 'rgba(46,160,67,0.12)'
                    : C.badSoft || 'rgba(248,81,73,0.12)',
                  borderColor: isStreamOnline
                    ? C.goodSoftBorder || 'rgba(46,160,67,0.25)'
                    : C.badSoftBorder || 'rgba(248,81,73,0.25)',
                },
              ]}
            >
              <Text
                style={[
                  styles.liveBadgeText,
                  {
                    color: isStreamOnline ? C.good || '#2ea043' : C.bad || '#f85149',
                  },
                ]}
              >
                {isStreamOnline ? 'LIVE' : 'OFFLINE'}
              </Text>
            </View>
          </View>

          <View style={styles.feedOuter}>
            <View style={{ width: '100%', maxWidth: feedMaxWidth }}>
              <StreamSurface borderColor={C.border} />
            </View>
          </View>

          <View style={[styles.liveStatusBar, { backgroundColor: C.card, borderColor: C.border }]}>
            <Text style={[styles.liveStatusText, { color: machine.leather_present ? C.accent : C.muted }]}>
              {liveStatusText}
            </Text>
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
          <Text style={[styles.sectionTitle, { color: C.text }]}>Machine / Segregation Status</Text>
          <View style={styles.machineGrid}>
            {renderMachineRow('Backend API', isBackendOnline ? 'ONLINE' : 'OFFLINE', isBackendOnline ? (C.good || '#2ea043') : (C.bad || '#f85149'))}
            {renderMachineRow('Stream Server', isStreamOnline ? 'ONLINE' : 'OFFLINE', isStreamOnline ? (C.good || '#2ea043') : (C.bad || '#f85149'))}
            {renderMachineRow('Arduino', isArduinoOnline ? 'CONNECTED' : 'DISCONNECTED', isArduinoOnline ? (C.good || '#2ea043') : (C.bad || '#f85149'))}
            {renderMachineRow('Leather Present', machine.leather_present ? 'YES' : 'NO', machine.leather_present ? C.accent : C.text)}
            {renderMachineRow('Servo', machine.servo_busy ? 'ACTIVE' : 'IDLE', machine.servo_busy ? (C.bad || '#f85149') : (C.good || '#2ea043'))}
            {renderMachineRow('Current Result', machine.current_result || 'WAITING FOR LEATHER', machine.current_result === 'BAD DETECTED' ? (C.bad || '#f85149') : C.accent)}
            {renderMachineRow('Bad Frames', machine.consecutive_bad_frames ?? 0, C.text)}
            {renderMachineRow('Max Defects Seen', machine.max_defects_seen ?? 0, C.text)}
            {renderMachineRow('Current Defect Count', machine.current_defect_count ?? 0, C.text)}
            {renderMachineRow('Last Command', machine.last_command_sent || '—', C.accent)}
            {renderMachineRow('Last Result', machine.last_result || '—', machine.last_result === 'BAD' ? (C.bad || '#f85149') : machine.last_result === 'GOOD' ? (C.good || '#2ea043') : C.text)}
          </View>
        </View>

        <View style={cardStyle}>
          <Text style={[styles.sectionTitle, { color: C.text }]}>Current Frame Detections</Text>
          <View style={styles.pillWrap}>
            {currentDetections?.length ? (
              currentDetections.map(renderDefectPill)
            ) : (
              <Text style={[styles.emptyText, { color: C.muted }]}>No live detections right now.</Text>
            )}
          </View>
        </View>

        <View style={cardStyle}>
          <Text style={[styles.sectionTitle, { color: C.text }]}>Inspection Event</Text>

          <View
            style={[
              styles.eventBanner,
              {
                backgroundColor: inspectionEvent.active
                  ? C.accentSoft || 'rgba(88,166,255,0.10)'
                  : C.bg,
                borderColor: inspectionEvent.active
                  ? C.accentSoftBorder || 'rgba(88,166,255,0.25)'
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
                <Text style={[styles.resultBadge, { color: getClassificationTone(latestResult.classification).text }]}>
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
                  style={[styles.historyItem, { backgroundColor: C.bg, borderColor: C.border }]}
                >
                  <View style={styles.historyTopRow}>
                    <Text style={[styles.historyHideId, { color: C.text }]}>{item.hide_id}</Text>
                    <View style={[styles.historyBadge, { backgroundColor: tone.bg, borderColor: tone.border }]}>
                      <Text style={[styles.historyBadgeText, { color: tone.text }]}>{item.classification}</Text>
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
              style={[styles.actionButton, { backgroundColor: C.bg, borderColor: C.border }]}
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
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    paddingHorizontal: 12,
    paddingTop: 12,
    paddingBottom: 30,
    alignItems: 'center',
  },
  contentWrap: {
    width: '100%',
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
    fontSize: 15,
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
  feedOuter: {
    alignItems: 'center',
    backgroundColor: '#000',
    borderRadius: 16,
  },
  videoWrap: {
    width: '100%',
    aspectRatio: 4 / 3,
    borderWidth: 1,
    borderRadius: 16,
    overflow: 'hidden',
    backgroundColor: '#000',
  },
  webview: {
    flex: 1,
    backgroundColor: '#000',
  },
  liveStatusBar: {
    marginTop: 12,
    borderWidth: 1,
    borderRadius: 12,
    paddingVertical: 10,
    paddingHorizontal: 12,
  },
  liveStatusText: {
    fontSize: 13,
    fontWeight: '800',
    textAlign: 'center',
    letterSpacing: 0.3,
  },
  statsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
  },
  statCard: {
    width: '48.5%',
    borderWidth: 1,
    borderRadius: 14,
    padding: 12,
    marginBottom: 10,
  },
  statLabel: {
    fontSize: 11,
    fontWeight: '700',
    textTransform: 'uppercase',
    letterSpacing: 0.8,
    marginBottom: 6,
  },
  statValue: {
    fontSize: 20,
    fontWeight: '900',
  },
  machineGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
  },
  machineRow: {
    width: '48.5%',
    borderWidth: 1,
    borderRadius: 14,
    padding: 12,
    marginBottom: 10,
  },
  machineLabel: {
    fontSize: 11,
    fontWeight: '700',
    textTransform: 'uppercase',
    letterSpacing: 0.8,
    marginBottom: 6,
  },
  machineValue: {
    fontSize: 15,
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
  },
  defectPill: {
    borderWidth: 1,
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 7,
    marginRight: 8,
    marginBottom: 8,
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
  },
  latestMetaText: {
    fontSize: 12,
    fontWeight: '600',
    marginBottom: 4,
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
    marginBottom: 10,
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
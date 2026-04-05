import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  RefreshControl,
  Dimensions,
  TouchableOpacity,
  ActivityIndicator,
  Animated,
} from 'react-native';
import { BarChart, PieChart } from 'react-native-chart-kit';
import StatCard from '../components/StatCard';
import { getAnalytics, getDefectDistribution, getTimeline } from '../services/inspectionService';
import { useAppTheme } from '../theme/AppThemeContext';

const SCREEN_WIDTH = Dimensions.get('window').width;
const CHART_WIDTH = SCREEN_WIDTH - 48;

const PERIODS = [
  { key: 'today', label: 'TODAY' },
  { key: 'week', label: '7D' },
  { key: 'month', label: '30D' },
  { key: 'all', label: 'ALL' },
];

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
        Animated.timing(opacity, { toValue: 1, duration: 500, useNativeDriver: true }),
        Animated.spring(translate, { toValue: 0, friction: 6, tension: 40, useNativeDriver: true }),
      ]),
    ]).start();
  }, [delay, direction, opacity, translate]);

  const transform =
    direction === 'up' || direction === 'down'
      ? [{ translateY: translate }]
      : [{ translateX: translate }];

  return <Animated.View style={[{ opacity, transform }, style]}>{children}</Animated.View>;
}

function AnimatedNumber({ value, color }) {
  const scale = useRef(new Animated.Value(0.5)).current;

  useEffect(() => {
    Animated.spring(scale, { toValue: 1, friction: 4, useNativeDriver: true }).start();
  }, [value, scale]);

  return (
    <Animated.Text
      style={{
        transform: [{ scale }],
        color,
        fontSize: 28,
        fontWeight: '900',
      }}
    >
      {value}
    </Animated.Text>
  );
}

export default function AnalyticsScreen() {
  const { theme: C } = useAppTheme();
  const styles = getStyles(C);
  const DEFECT_COLORS = [C.accent, C.bad, C.blue, C.dim, C.good];

  const [period, setPeriod] = useState('today');
  const [analytics, setAnalytics] = useState(null);
  const [defectDist, setDefectDist] = useState([]);
  const [timeline, setTimeline] = useState([]);
  const [refreshing, setRefreshing] = useState(false);
  const [loading, setLoading] = useState(true);

  const gaugeWidth = useRef(new Animated.Value(0)).current;
  const periodScale = useRef(new Animated.Value(1)).current;

  const loadData = useCallback(async () => {
    try {
      const [a, d, t] = await Promise.all([
        getAnalytics(period),
        getDefectDistribution(period),
        getTimeline(period),
      ]);

      if (a) {
        setAnalytics(a);
        Animated.spring(gaugeWidth, {
          toValue: a.pass_rate || 0,
          friction: 6,
          useNativeDriver: false,
        }).start();
      }

      if (d?.defects) setDefectDist(d.defects);
      if (t?.timeline) setTimeline(t.timeline);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [period, gaugeWidth]);

  useEffect(() => {
    setLoading(true);
    loadData();
  }, [period, loadData]);

  useEffect(() => {
    const i = setInterval(loadData, 30000);
    return () => clearInterval(i);
  }, [loadData]);

  const animatePeriodPress = () => {
    Animated.sequence([
      Animated.timing(periodScale, { toValue: 0.95, duration: 100, useNativeDriver: true }),
      Animated.spring(periodScale, { toValue: 1, friction: 3, useNativeDriver: true }),
    ]).start();
  };

  const barChartData = {
    labels: timeline.length > 0 ? timeline.map((t) => t.time_label || '') : ['—'],
    datasets: [
      { data: timeline.length > 0 ? timeline.map((t) => t.good || 0) : [0], color: () => C.good },
      { data: timeline.length > 0 ? timeline.map((t) => t.bad || 0) : [0], color: () => C.bad },
    ],
    legend: ['Passed', 'Failed'],
  };

  const pieData =
    defectDist.length > 0
      ? defectDist.map((d, i) => ({
          name: (d.type || '?').replace(/_/g, ' '),
          count: d.count,
          color: DEFECT_COLORS[i % DEFECT_COLORS.length],
          legendFontColor: C.dim,
          legendFontSize: 11,
        }))
      : [
          {
            name: 'None',
            count: 1,
            color: C.muted,
            legendFontColor: C.muted,
            legendFontSize: 11,
          },
        ];

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color={C.accent} />
        <Text style={styles.loadingText}>LOADING ANALYTICS</Text>
      </View>
    );
  }

  const gaugePercent = gaugeWidth.interpolate({
    inputRange: [0, 100],
    outputRange: ['0%', '100%'],
  });

  return (
    <ScrollView
      style={styles.container}
      refreshControl={
        <RefreshControl
          refreshing={refreshing}
          onRefresh={() => {
            setRefreshing(true);
            loadData();
          }}
          tintColor={C.accent}
          colors={[C.accent]}
        />
      }
    >
      <FadeSlideIn delay={0} direction="down">
        <View style={styles.periodBar}>
          {PERIODS.map((opt) => (
            <Animated.View
              key={`period-${opt.key}`}
              style={{
                flex: 1,
                transform: [{ scale: period === opt.key ? periodScale : 1 }],
              }}
            >
              <TouchableOpacity
                style={[styles.periodBtn, period === opt.key && styles.periodActive]}
                onPress={() => {
                  setPeriod(opt.key);
                  animatePeriodPress();
                }}
              >
                <Text style={[styles.periodText, period === opt.key && styles.periodTextActive]}>
                  {opt.label}
                </Text>
              </TouchableOpacity>
            </Animated.View>
          ))}
        </View>
      </FadeSlideIn>

      {analytics && (
        <FadeSlideIn delay={100} direction="up">
          <View style={styles.section}>
            <View style={styles.sectionHeader}>
              <Text style={styles.sectionDot}>●</Text>
              <Text style={styles.sectionTitle}>OVERVIEW</Text>
            </View>

            <View style={styles.statsRow}>
              <StatCard label="Inspected" value={analytics.total_inspections} icon="◈" color={C.blue} theme={C} />
              <StatCard label="Passed" value={analytics.good_count} icon="▲" color={C.good} theme={C} />
              <StatCard label="Failed" value={analytics.bad_count} icon="▼" color={C.bad} theme={C} />
            </View>

            <View style={styles.statsRow}>
              <StatCard label="Pass Rate" value={analytics.pass_rate} unit="%" icon="◆" color={C.good} theme={C} />
              <StatCard label="Fail Rate" value={analytics.defect_rate} unit="%" icon="◆" color={C.bad} theme={C} />
              <StatCard
                label="Avg Defects"
                value={analytics.avg_defects_per_hide}
                icon="◆"
                color={C.accent}
                theme={C}
              />
            </View>
          </View>
        </FadeSlideIn>
      )}

      {analytics && analytics.total_inspections > 0 && (
        <FadeSlideIn delay={200} direction="up">
          <View style={styles.section}>
            <View style={styles.gaugeCard}>
              <View style={styles.gaugeHeader}>
                <Text style={styles.gaugeTitle}>QUALITY INDEX</Text>
                <AnimatedNumber
                  value={analytics.pass_rate}
                  color={analytics.pass_rate >= 70 ? C.good : C.bad}
                />
              </View>

              <View style={styles.gaugeBarBg}>
                <Animated.View style={[styles.gaugeBarGood, { width: gaugePercent }]} />
              </View>

              <View style={styles.gaugeLegend}>
                <View style={styles.gaugeLegendItem}>
                  <View style={[styles.gaugeLegendDot, { backgroundColor: C.good }]} />
                  <Text style={styles.gaugeLegendText}>Passed ({analytics.good_count})</Text>
                </View>

                <View style={styles.gaugeLegendItem}>
                  <View style={[styles.gaugeLegendDot, { backgroundColor: C.bad }]} />
                  <Text style={styles.gaugeLegendText}>Failed ({analytics.bad_count})</Text>
                </View>
              </View>
            </View>
          </View>
        </FadeSlideIn>
      )}

      {timeline.length > 0 && (
        <FadeSlideIn delay={300} direction="up">
          <View style={styles.section}>
            <View style={styles.sectionHeader}>
              <Text style={styles.sectionDot}>●</Text>
              <Text style={styles.sectionTitle}>INSPECTION TIMELINE</Text>
            </View>

            <View style={styles.chartCard}>
              <BarChart
                data={barChartData}
                width={CHART_WIDTH}
                height={200}
                fromZero
                showBarTops={false}
                chartConfig={{
                  backgroundGradientFrom: C.card,
                  backgroundGradientTo: C.card,
                  decimalPlaces: 0,
                  color: (opacity = 1) => `rgba(88,166,255,${opacity})`,
                  labelColor: () => C.muted,
                  barPercentage: 0.4,
                  propsForBackgroundLines: { strokeDasharray: '3 6', stroke: C.border },
                }}
                style={{ borderRadius: 10 }}
              />
            </View>
          </View>
        </FadeSlideIn>
      )}

      <FadeSlideIn delay={400} direction="up">
        <View style={styles.section}>
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionDot}>●</Text>
            <Text style={styles.sectionTitle}>DEFECT DISTRIBUTION</Text>
          </View>

          <View style={styles.chartCard}>
            <PieChart
              data={pieData}
              width={CHART_WIDTH}
              height={180}
              chartConfig={{ color: () => C.text }}
              accessor="count"
              backgroundColor="transparent"
              paddingLeft="15"
              absolute
            />
          </View>
        </View>
      </FadeSlideIn>

      {defectDist.length > 0 && (
        <FadeSlideIn delay={500} direction="up">
          <View style={styles.section}>
            <View style={styles.sectionHeader}>
              <Text style={styles.sectionDot}>●</Text>
              <Text style={styles.sectionTitle}>DEFECT BREAKDOWN</Text>
            </View>

            <View style={styles.tableCard}>
              <View style={styles.tableHeader}>
                <Text style={[styles.thText, { flex: 2 }]}>TYPE</Text>
                <Text style={[styles.thText, { flex: 1, textAlign: 'center' }]}>COUNT</Text>
                <Text style={[styles.thText, { flex: 1, textAlign: 'right' }]}>SHARE</Text>
              </View>

              {defectDist.map((d, i) => {
                const total = defectDist.reduce((s, x) => s + x.count, 0);
                const share = total > 0 ? ((d.count / total) * 100).toFixed(1) : 0;
                const color = DEFECT_COLORS[i % DEFECT_COLORS.length];

                return (
                  <FadeSlideIn key={`defect-row-${i}-${d.type}`} delay={600 + i * 80} direction="right">
                    <View style={styles.tableRow}>
                      <View style={[styles.td, { flex: 2, flexDirection: 'row', alignItems: 'center' }]}>
                        <View style={[styles.tdDot, { backgroundColor: color }]} />
                        <Text style={styles.tdText}>{(d.type || '?').replace(/_/g, ' ')}</Text>
                      </View>

                      <Text style={[styles.tdText, { flex: 1, textAlign: 'center', fontWeight: '800', color }]}>
                        {d.count}
                      </Text>

                      <View style={[styles.td, { flex: 1, alignItems: 'flex-end' }]}>
                        <View style={styles.shareBadge}>
                          <Text style={styles.shareText}>{share}%</Text>
                        </View>
                      </View>
                    </View>
                  </FadeSlideIn>
                );
              })}
            </View>
          </View>
        </FadeSlideIn>
      )}

      <View style={{ height: 40 }} />
    </ScrollView>
  );
}

const getStyles = (C) =>
  StyleSheet.create({
    container: { flex: 1, backgroundColor: C.bg },
    center: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: C.bg },
    loadingText: { marginTop: 16, fontSize: 11, color: C.accent, fontWeight: '800', letterSpacing: 2 },

    periodBar: {
      flexDirection: 'row',
      paddingHorizontal: 16,
      paddingVertical: 12,
      gap: 8,
      backgroundColor: C.card,
      borderBottomWidth: 1,
      borderBottomColor: C.border,
    },
    periodBtn: {
      paddingVertical: 8,
      borderRadius: 6,
      alignItems: 'center',
      backgroundColor: C.bg,
      borderWidth: 1,
      borderColor: C.border,
    },
    periodActive: { backgroundColor: C.accent, borderColor: C.accent },
    periodText: { fontSize: 11, fontWeight: '800', color: C.muted, letterSpacing: 1 },
    periodTextActive: { color: C.white },

    section: { paddingHorizontal: 16, marginTop: 20 },
    sectionHeader: { flexDirection: 'row', alignItems: 'center', marginBottom: 12 },
    sectionDot: { color: C.accent, fontSize: 8, marginRight: 8 },
    sectionTitle: { fontSize: 11, fontWeight: '800', color: C.dim, letterSpacing: 1.5 },
    statsRow: { flexDirection: 'row', marginBottom: 8 },

    gaugeCard: {
      backgroundColor: C.card,
      borderRadius: 12,
      padding: 16,
      borderWidth: 1,
      borderColor: C.border,
    },
    gaugeHeader: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'center',
      marginBottom: 12,
    },
    gaugeTitle: { fontSize: 10, fontWeight: '800', color: C.dim, letterSpacing: 1.5 },
    gaugeBarBg: { height: 10, borderRadius: 5, overflow: 'hidden', backgroundColor: C.bad },
    gaugeBarGood: { height: 10, backgroundColor: C.good, borderRadius: 5 },
    gaugeLegend: { flexDirection: 'row', justifyContent: 'center', marginTop: 10, gap: 20 },
    gaugeLegendItem: { flexDirection: 'row', alignItems: 'center' },
    gaugeLegendDot: { width: 8, height: 8, borderRadius: 4, marginRight: 6 },
    gaugeLegendText: { fontSize: 11, color: C.dim },

    chartCard: {
      backgroundColor: C.card,
      borderRadius: 12,
      padding: 12,
      borderWidth: 1,
      borderColor: C.border,
      alignItems: 'center',
    },

    tableCard: {
      backgroundColor: C.card,
      borderRadius: 12,
      overflow: 'hidden',
      borderWidth: 1,
      borderColor: C.border,
    },
    tableHeader: {
      flexDirection: 'row',
      paddingVertical: 10,
      paddingHorizontal: 14,
      borderBottomWidth: 1,
      borderBottomColor: C.border,
      backgroundColor: C.subtle2,
    },
    thText: { fontSize: 9, fontWeight: '800', color: C.muted, letterSpacing: 1.5 },
    tableRow: {
      flexDirection: 'row',
      paddingVertical: 12,
      paddingHorizontal: 14,
      borderBottomWidth: 1,
      borderBottomColor: C.dividerSoft,
      alignItems: 'center',
    },
    td: {},
    tdDot: { width: 8, height: 8, borderRadius: 4, marginRight: 10 },
    tdText: { fontSize: 13, color: C.text },
    shareBadge: {
      backgroundColor: C.subtle,
      borderRadius: 4,
      paddingHorizontal: 8,
      paddingVertical: 2,
    },
    shareText: { fontSize: 11, color: C.dim, fontWeight: '600', fontFamily: 'monospace' },
  });
import React from 'react';
import { View, Text, StyleSheet } from 'react-native';

const DEFECT_CONFIG = {
  color_defect: { color: '#f0883e', icon: '◆', label: 'Color Defect' },
  hole: { color: '#f85149', icon: '◉', label: 'Hole' },
  fold: { color: '#58a6ff', icon: '◫', label: 'Fold' },
  default: { color: '#8b949e', icon: '◈', label: 'Unknown' },
};

const defaultTheme = {
  card: '#161b22',
  border: '#30363d',
  text: '#e6edf3',
  muted: '#484f58',
  barBg: '#21262d',
};

export default function DefectCard({ defect, theme }) {
  const C = theme || defaultTheme;
  const config = DEFECT_CONFIG[defect.type] || DEFECT_CONFIG.default;
  const confidence = Math.round((defect.confidence || 0) * 100);

  return (
    <View style={[styles.card, { backgroundColor: C.card, borderColor: C.border, borderLeftColor: config.color }]}>
      <View style={styles.row}>
        <View style={styles.left}>
          <View style={styles.typeRow}>
            <Text style={[styles.icon, { color: config.color }]}>{config.icon}</Text>
            <Text style={[styles.type, { color: C.text }]}>{config.label}</Text>
          </View>

          {defect.x !== undefined && defect.y !== undefined && (
            <Text style={[styles.location, { color: C.muted }]}>
              ({defect.x}, {defect.y}) · {defect.w}×{defect.h}
            </Text>
          )}
        </View>

        <View style={styles.right}>
          <Text style={[styles.confidence, { color: config.color }]}>{confidence}</Text>
          <Text style={[styles.percent, { color: C.muted }]}>%</Text>
        </View>
      </View>

      <View style={[styles.barBg, { backgroundColor: C.barBg }]}>
        <View
          style={[
            styles.barFill,
            {
              width: `${confidence}%`,
              backgroundColor: config.color,
            },
          ]}
        />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderLeftWidth: 3,
    borderRadius: 8,
    padding: 14,
    marginBottom: 8,
    borderWidth: 1,
  },
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  left: { flex: 1 },
  typeRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  icon: {
    fontSize: 14,
    marginRight: 8,
  },
  type: {
    fontSize: 14,
    fontWeight: '700',
    letterSpacing: 0.3,
  },
  location: {
    fontSize: 11,
    marginTop: 4,
    fontFamily: 'monospace',
    letterSpacing: 0.5,
  },
  right: {
    flexDirection: 'row',
    alignItems: 'baseline',
  },
  confidence: {
    fontSize: 24,
    fontWeight: '900',
  },
  percent: {
    fontSize: 12,
    fontWeight: '600',
    marginLeft: 1,
  },
  barBg: {
    height: 3,
    borderRadius: 2,
    marginTop: 10,
    overflow: 'hidden',
  },
  barFill: {
    height: 3,
    borderRadius: 2,
  },
});
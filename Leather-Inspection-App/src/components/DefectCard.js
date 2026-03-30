import React from 'react';
import { View, Text, StyleSheet } from 'react-native';

const DEFECT_CONFIG = {
  color_defect: { color: '#f0883e', icon: '◆', label: 'Color Defect' },
  hole: { color: '#f85149', icon: '◉', label: 'Hole' },
  fold: { color: '#58a6ff', icon: '◫', label: 'Fold' },
  default: { color: '#8b949e', icon: '◈', label: 'Unknown' },
};

export default function DefectCard({ defect }) {
  const config = DEFECT_CONFIG[defect.type] || DEFECT_CONFIG.default;
  const confidence = Math.round((defect.confidence || 0) * 100);

  return (
    <View style={[styles.card, { borderLeftColor: config.color }]}>
      <View style={styles.row}>
        <View style={styles.left}>
          <View style={styles.typeRow}>
            <Text style={[styles.icon, { color: config.color }]}>{config.icon}</Text>
            <Text style={styles.type}>{config.label}</Text>
          </View>
          {(defect.x !== undefined && defect.y !== undefined) && (
            <Text style={styles.location}>
              ({defect.x}, {defect.y}) · {defect.w}×{defect.h}
            </Text>
          )}
        </View>
        <View style={styles.right}>
          <Text style={[styles.confidence, { color: config.color }]}>{confidence}</Text>
          <Text style={styles.percent}>%</Text>
        </View>
      </View>
      <View style={styles.barBg}>
        <View style={[styles.barFill, { width: `${confidence}%`, backgroundColor: config.color }]} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: '#161b22',
    borderLeftWidth: 3,
    borderRadius: 8,
    padding: 14,
    marginBottom: 8,
    borderColor: '#30363d',
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
    color: '#e6edf3',
    letterSpacing: 0.3,
  },
  location: {
    fontSize: 11,
    color: '#484f58',
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
    color: '#484f58',
    fontWeight: '600',
    marginLeft: 1,
  },
  barBg: {
    height: 3,
    backgroundColor: '#21262d',
    borderRadius: 2,
    marginTop: 10,
    overflow: 'hidden',
  },
  barFill: {
    height: 3,
    borderRadius: 2,
  },
});
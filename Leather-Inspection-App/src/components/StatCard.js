import React from 'react';
import { View, Text, StyleSheet } from 'react-native';

export default function StatCard({ label, value, unit = '', color = '#58a6ff', icon = '' }) {
  return (
    <View style={styles.card}>
      <View style={[styles.accent, { backgroundColor: color }]} />
      <View style={styles.content}>
        {icon ? <Text style={styles.icon}>{icon}</Text> : null}
        <Text style={[styles.value, { color }]}>
          {value}
          {unit ? <Text style={styles.unit}>{unit}</Text> : null}
        </Text>
        <Text style={styles.label}>{label}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: '#161b22',
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#30363d',
    flex: 1,
    margin: 4,
    overflow: 'hidden',
  },
  accent: {
    height: 3,
    width: '100%',
  },
  content: {
    padding: 14,
    alignItems: 'center',
  },
  icon: {
    fontSize: 18,
    marginBottom: 4,
  },
  value: {
    fontSize: 26,
    fontWeight: '900',
    letterSpacing: -0.5,
  },
  unit: {
    fontSize: 13,
    fontWeight: '500',
  },
  label: {
    fontSize: 9,
    color: '#484f58',
    marginTop: 6,
    textTransform: 'uppercase',
    letterSpacing: 1.5,
    fontWeight: '700',
  },
});
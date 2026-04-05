import React from 'react';
import { View, Text, StyleSheet } from 'react-native';

const defaultTheme = {
  card: '#161b22',
  border: '#30363d',
  muted: '#484f58',
};

export default function StatCard({
  label,
  value,
  unit = '',
  color = '#58a6ff',
  icon = '',
  theme,
}) {
  const C = theme || defaultTheme;

  return (
    <View style={[styles.card, { backgroundColor: C.card, borderColor: C.border }]}>
      <View style={[styles.accent, { backgroundColor: color }]} />
      <View style={styles.content}>
        {icon ? <Text style={styles.icon}>{icon}</Text> : null}

        <Text style={[styles.value, { color }]}>
          {value}
          {unit ? <Text style={[styles.unit, { color }]}>{unit}</Text> : null}
        </Text>

        <Text style={[styles.label, { color: C.muted }]}>{label}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: 10,
    borderWidth: 1,
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
    marginTop: 6,
    fontSize: 9,
    textTransform: 'uppercase',
    letterSpacing: 1.5,
    fontWeight: '700',
  },
});
import React, { useEffect, useRef } from 'react';
import { View, Text, StyleSheet, ScrollView, Animated } from 'react-native';
import { useAppTheme } from '../theme/AppThemeContext';

const TEAM_MEMBERS = [
  'Christian G. Bondoc',
  'Keneth M. Campo',
  'Audrick Zander G. Cuadra',
  'Gwyneth D. Esperat',
  'Pamela V. Malazarte',
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
  }, []);

  const transform =
    direction === 'up' || direction === 'down'
      ? [{ translateY: translate }]
      : [{ translateX: translate }];

  return <Animated.View style={[{ opacity, transform }, style]}>{children}</Animated.View>;
}

export default function AboutScreen() {
  const { theme: C } = useAppTheme();
  const styles = getStyles(C);

  const DEFECT_TYPES = [
    {
      name: 'Color Defects',
      icon: '◆',
      color: C.accent,
      desc: 'Discoloration, stains, or uneven dye on the leather surface',
    },
    {
      name: 'Holes',
      icon: '◉',
      color: C.bad,
      desc: 'Punctures, perforations, or missing material in the hide',
    },
    {
      name: 'Folds',
      icon: '◫',
      color: C.blue,
      desc: 'Creases, wrinkles, or folded areas affecting surface quality',
    },
  ];

  const STANDARDS = [
    { code: 'ISO 17551:2018', title: 'Grading of pickled sheep pelts based on defect and size' },
    { code: 'ISO 11457:2018', title: 'Grading of wet blue goat and sheep skins based on defects' },
    { code: 'IEC 60204-1', title: 'Safety of machinery — Electrical equipment of machines' },
    { code: 'ISO/IEC TS 4213:2022', title: 'Assessment of machine learning classification performance' },
  ];

  const ARCH_STATIONS = [
    {
      num: '01',
      name: 'Feeding & Transport',
      desc: 'Friction rollers guide the leather hide through the inspection path',
      color: C.blue,
    },
    {
      num: '02',
      name: 'Inspection & Projection',
      desc: 'Camera captures images, deep learning detects defects, projector overlays results',
      color: C.accent,
    },
    {
      num: '03',
      name: 'Marking Module',
      desc: 'Encoder-synchronized marking applies non-invasive stamps on defect locations',
      color: C.bad,
    },
    {
      num: '04',
      name: 'Sorting & Segregation',
      desc: 'Motorized diverter routes hides into Good or Bad bins automatically',
      color: C.good,
    },
  ];

  const TECH_STACK = [
    ['Processing Unit', 'Raspberry Pi 5 (8GB)'],
    ['Controller', 'Arduino Uno'],
    ['Detection Model', 'YOLOv8n'],
    ['Framework', 'Ultralytics / PyTorch'],
    ['Vision Library', 'OpenCV'],
    ['Mobile App', 'React Native / Expo'],
    ['Backend API', 'Flask + SQLite'],
  ];

  return (
    <ScrollView style={styles.container}>
      <FadeSlideIn delay={0} direction="down">
        <View style={styles.heroCard}>
          <View style={styles.heroAccent} />
          <View style={styles.heroContent}>
            <Text style={styles.heroLabel}>CAPSTONE DESIGN PROJECT</Text>
            <Text style={styles.heroAppName}>HideSpec</Text>
            <Text style={styles.heroTitle}>
              Deep Learning-Based Defect Classification for Leather Hides Inspection
            </Text>
            <Text style={styles.heroSubtitle}>with Segregation System</Text>
            <View style={styles.heroDivider} />
            <Text style={styles.heroSchool}>Technological Institute of the Philippines</Text>
            <Text style={styles.heroDetails}>Computer Engineering Department · Quezon City</Text>
            <Text style={styles.heroDetails}>2nd Semester, SY 2025–2026 · Team 10</Text>
          </View>
        </View>
      </FadeSlideIn>

      <View style={styles.section}>
        <FadeSlideIn delay={100} direction="up">
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionDot}>●</Text>
            <Text style={styles.sectionTitle}>DETECTABLE DEFECTS</Text>
          </View>
        </FadeSlideIn>

        {DEFECT_TYPES.map((d, i) => (
          <FadeSlideIn key={`defect-${i}`} delay={200 + i * 100} direction="left">
            <View style={[styles.defectTypeCard, { borderLeftColor: d.color }]}>
              <View style={styles.defectTypeHeader}>
                <Text style={[styles.defectTypeIcon, { color: d.color }]}>{d.icon}</Text>
                <Text style={styles.defectTypeName}>{d.name}</Text>
              </View>
              <Text style={styles.defectTypeDesc}>{d.desc}</Text>
            </View>
          </FadeSlideIn>
        ))}
      </View>

      <View style={styles.section}>
        <FadeSlideIn delay={500} direction="up">
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionDot}>●</Text>
            <Text style={styles.sectionTitle}>SYSTEM ARCHITECTURE</Text>
          </View>
        </FadeSlideIn>

        <FadeSlideIn delay={600} direction="up">
          <View style={styles.archCard}>
            {ARCH_STATIONS.map((station, i) => (
              <FadeSlideIn key={`station-${i}`} delay={700 + i * 120} direction="right">
                <View>
                  <View style={styles.archStation}>
                    <View
                      style={[
                        styles.archBadge,
                        {
                          backgroundColor: `${station.color}15`,
                          borderColor: `${station.color}40`,
                        },
                      ]}
                    >
                      <Text style={[styles.archBadgeText, { color: station.color }]}>{station.num}</Text>
                    </View>

                    <View style={styles.archInfo}>
                      <Text style={styles.archName}>{station.name}</Text>
                      <Text style={styles.archDesc}>{station.desc}</Text>
                    </View>
                  </View>

                  {i < ARCH_STATIONS.length - 1 && <View style={styles.archLine} />}
                </View>
              </FadeSlideIn>
            ))}
          </View>
        </FadeSlideIn>
      </View>

      <View style={styles.section}>
        <FadeSlideIn delay={1100} direction="up">
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionDot}>●</Text>
            <Text style={styles.sectionTitle}>TECHNOLOGY STACK</Text>
          </View>

          <View style={styles.techCard}>
            {TECH_STACK.map(([label, value], i) => (
              <FadeSlideIn key={`tech-${i}`} delay={1200 + i * 60} direction="right">
                <View style={[styles.techRow, i === TECH_STACK.length - 1 && { borderBottomWidth: 0 }]}>
                  <Text style={styles.techLabel}>{label}</Text>
                  <Text style={styles.techValue}>{value}</Text>
                </View>
              </FadeSlideIn>
            ))}
          </View>
        </FadeSlideIn>
      </View>

      <View style={styles.section}>
        <FadeSlideIn delay={1600} direction="up">
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionDot}>●</Text>
            <Text style={styles.sectionTitle}>ENGINEERING STANDARDS</Text>
          </View>
        </FadeSlideIn>

        {STANDARDS.map((s, i) => (
          <FadeSlideIn key={`std-${i}`} delay={1700 + i * 80} direction="left">
            <View style={styles.standardItem}>
              <Text style={styles.standardCode}>{s.code}</Text>
              <Text style={styles.standardTitle}>{s.title}</Text>
            </View>
          </FadeSlideIn>
        ))}
      </View>

      <FadeSlideIn delay={2100} direction="up">
        <View style={styles.section}>
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionDot}>●</Text>
            <Text style={styles.sectionTitle}>CLIENT</Text>
          </View>
          <View style={styles.clientCard}>
            <Text style={styles.clientName}>Cpoint Shoes Marikina</Text>
            <Text style={styles.clientDesc}>
              A small-to-medium shoe manufacturer based in Marikina City, Philippines — the national Shoe
              Capital. The company focuses on manufacturing leather shoes and relies on manual inspection of
              leather hides for quality control.
            </Text>
          </View>
        </View>
      </FadeSlideIn>

      <View style={styles.section}>
        <FadeSlideIn delay={2200} direction="up">
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionDot}>●</Text>
            <Text style={styles.sectionTitle}>TEAM MEMBERS</Text>
          </View>
        </FadeSlideIn>

        <FadeSlideIn delay={2300} direction="up">
          <View style={styles.teamCard}>
            {TEAM_MEMBERS.map((name, i) => (
              <FadeSlideIn key={`member-${i}`} delay={2400 + i * 80} direction="right">
                <View style={styles.teamMember}>
                  <View style={styles.teamAvatar}>
                    <Text style={styles.teamInitial}>{name.charAt(0)}</Text>
                  </View>
                  <Text style={styles.teamName}>{name}</Text>
                </View>
              </FadeSlideIn>
            ))}

            <View style={styles.teamDivider} />

            <FadeSlideIn delay={2800} direction="right">
              <View style={styles.teamMember}>
                <View style={[styles.teamAvatar, styles.adviserAvatar]}>
                  <Text style={[styles.teamInitial, { color: C.accent }]}>A</Text>
                </View>
                <View>
                  <Text style={styles.teamName}>Engr. Neal Barton James Matira</Text>
                  <Text style={styles.teamRole}>Project Adviser</Text>
                </View>
              </View>
            </FadeSlideIn>
          </View>
        </FadeSlideIn>
      </View>

      <FadeSlideIn delay={2900} direction="up">
        <View style={styles.footer}>
          <Text style={styles.footerText}>CPE DESIGN PROJECT</Text>
          <Text style={styles.footerSub}>Technological Institute of the Philippines · Quezon City</Text>
          <Text style={styles.footerSub}>2nd Semester, SY 2025–2026</Text>
        </View>
      </FadeSlideIn>

      <View style={{ height: 40 }} />
    </ScrollView>
  );
}

const getStyles = (C) =>
  StyleSheet.create({
    container: { flex: 1, backgroundColor: C.bg },

    heroCard: {
      backgroundColor: C.card,
      borderBottomWidth: 1,
      borderBottomColor: C.border,
      overflow: 'hidden',
    },
    heroAccent: { height: 4, backgroundColor: C.accent },
    heroContent: { padding: 20 },
    heroLabel: { fontSize: 9, fontWeight: '800', color: C.accent, letterSpacing: 2, marginBottom: 10 },
    heroAppName: { fontSize: 32, fontWeight: '900', color: C.accent, letterSpacing: -1, marginBottom: 6 },
    heroTitle: { fontSize: 20, fontWeight: '900', color: C.text, lineHeight: 26, letterSpacing: -0.3 },
    heroSubtitle: { fontSize: 14, color: C.dim, marginTop: 4, fontStyle: 'italic' },
    heroDivider: { height: 1, backgroundColor: C.border, marginVertical: 14 },
    heroSchool: { fontSize: 13, fontWeight: '700', color: C.text },
    heroDetails: { fontSize: 11, color: C.muted, marginTop: 3 },

    section: { paddingHorizontal: 16, marginTop: 24 },
    sectionHeader: { flexDirection: 'row', alignItems: 'center', marginBottom: 12 },
    sectionDot: { color: C.accent, fontSize: 8, marginRight: 8 },
    sectionTitle: { fontSize: 11, fontWeight: '800', color: C.dim, letterSpacing: 1.5 },

    defectTypeCard: {
      backgroundColor: C.card,
      borderRadius: 10,
      padding: 14,
      marginBottom: 8,
      borderWidth: 1,
      borderColor: C.border,
      borderLeftWidth: 3,
    },
    defectTypeHeader: { flexDirection: 'row', alignItems: 'center', marginBottom: 6 },
    defectTypeIcon: { fontSize: 14, marginRight: 8 },
    defectTypeName: { fontSize: 14, fontWeight: '700', color: C.text },
    defectTypeDesc: { fontSize: 12, color: C.dim, lineHeight: 18 },

    archCard: {
      backgroundColor: C.card,
      borderRadius: 12,
      padding: 16,
      borderWidth: 1,
      borderColor: C.border,
    },
    archStation: { flexDirection: 'row', alignItems: 'flex-start' },
    archBadge: {
      width: 36,
      height: 36,
      borderRadius: 8,
      justifyContent: 'center',
      alignItems: 'center',
      marginRight: 14,
      borderWidth: 1,
    },
    archBadgeText: { fontSize: 12, fontWeight: '900' },
    archInfo: { flex: 1 },
    archName: { fontSize: 13, fontWeight: '700', color: C.text },
    archDesc: { fontSize: 11, color: C.dim, marginTop: 3, lineHeight: 16 },
    archLine: { width: 2, height: 16, backgroundColor: C.border, marginLeft: 17, marginVertical: 4 },

    techCard: {
      backgroundColor: C.card,
      borderRadius: 12,
      borderWidth: 1,
      borderColor: C.border,
      overflow: 'hidden',
    },
    techRow: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'center',
      paddingVertical: 12,
      paddingHorizontal: 14,
      borderBottomWidth: 1,
      borderBottomColor: C.dividerSoft,
    },
    techLabel: { fontSize: 12, color: C.muted, fontWeight: '600' },
    techValue: { fontSize: 12, color: C.text, fontWeight: '700' },

    standardItem: {
      backgroundColor: C.card,
      borderRadius: 10,
      padding: 14,
      marginBottom: 8,
      borderWidth: 1,
      borderColor: C.border,
    },
    standardCode: { fontSize: 11, fontWeight: '800', color: C.blue, letterSpacing: 0.5, marginBottom: 4 },
    standardTitle: { fontSize: 12, color: C.dim, lineHeight: 17 },

    clientCard: {
      backgroundColor: C.card,
      borderRadius: 12,
      padding: 16,
      borderWidth: 1,
      borderColor: C.border,
    },
    clientName: { fontSize: 16, fontWeight: '800', color: C.text, marginBottom: 8 },
    clientDesc: { fontSize: 12, color: C.dim, lineHeight: 19 },

    teamCard: {
      backgroundColor: C.card,
      borderRadius: 12,
      padding: 14,
      borderWidth: 1,
      borderColor: C.border,
    },
    teamMember: { flexDirection: 'row', alignItems: 'center', paddingVertical: 8 },
    teamAvatar: {
      width: 34,
      height: 34,
      borderRadius: 17,
      backgroundColor: `${C.blue}15`,
      borderWidth: 1,
      borderColor: `${C.blue}4D`,
      justifyContent: 'center',
      alignItems: 'center',
      marginRight: 12,
    },
    adviserAvatar: {
      backgroundColor: `${C.accent}15`,
      borderColor: `${C.accent}4D`,
    },
    teamInitial: { fontSize: 13, fontWeight: '800', color: C.blue },
    teamName: { fontSize: 13, fontWeight: '600', color: C.text },
    teamRole: { fontSize: 10, color: C.accent, fontWeight: '600', marginTop: 1, letterSpacing: 0.5 },
    teamDivider: { height: 1, backgroundColor: C.border, marginVertical: 8 },

    footer: { alignItems: 'center', paddingVertical: 30, marginTop: 10 },
    footerText: { fontSize: 10, fontWeight: '800', color: C.muted, letterSpacing: 2 },
    footerSub: { fontSize: 10, color: C.muted, marginTop: 3 },
  });
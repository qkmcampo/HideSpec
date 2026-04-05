import React, { useState, useRef, useEffect } from 'react';
import { Text, StatusBar, View, Animated, TouchableOpacity } from 'react-native';
import { NavigationContainer } from '@react-navigation/native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import LoginScreen from './src/screens/LoginScreen';
import LiveMonitorScreen from './src/screens/LiveMonitorScreen';
import AnalyticsScreen from './src/screens/AnalyticsScreen';
import AboutScreen from './src/screens/AboutScreen';
import { AppThemeProvider, useAppTheme } from './src/theme/AppThemeContext';

const Tab = createBottomTabNavigator();

function MainApp({ user, onLogout }) {
  const { theme: C, themeMode, toggleTheme } = useAppTheme();

  const fadeIn = useRef(new Animated.Value(0)).current;
  const slideUp = useRef(new Animated.Value(30)).current;

  useEffect(() => {
    Animated.parallel([
      Animated.timing(fadeIn, { toValue: 1, duration: 500, useNativeDriver: true }),
      Animated.spring(slideUp, { toValue: 0, friction: 6, useNativeDriver: true }),
    ]).start();
  }, [fadeIn, slideUp]);

  return (
    <Animated.View style={{ flex: 1, opacity: fadeIn, transform: [{ translateY: slideUp }] }}>
      <NavigationContainer>
        <StatusBar
          barStyle={themeMode === 'dark' ? 'light-content' : 'dark-content'}
          backgroundColor={C.card}
        />

        <Tab.Navigator
          screenOptions={{
            headerStyle: {
              backgroundColor: C.card,
              elevation: 0,
              shadowOpacity: 0,
              borderBottomWidth: 1,
              borderBottomColor: C.border,
            },
            headerTintColor: C.text,
            headerTitleStyle: {
              fontWeight: '800',
              fontSize: 14,
              letterSpacing: 0.3,
            },
            headerRight: () => (
              <View style={{ flexDirection: 'row', alignItems: 'center', marginRight: 12 }}>
                <TouchableOpacity
                  onPress={toggleTheme}
                  style={{
                    marginRight: 10,
                    backgroundColor: C.bg,
                    borderRadius: 6,
                    paddingHorizontal: 10,
                    paddingVertical: 5,
                    borderWidth: 1,
                    borderColor: C.border,
                  }}
                >
                  <Text
                    style={{
                      color: C.text,
                      fontSize: 10,
                      fontWeight: '800',
                      letterSpacing: 1,
                    }}
                  >
                    {themeMode === 'dark' ? 'LIGHT' : 'DARK'}
                  </Text>
                </TouchableOpacity>

                <TouchableOpacity
                  onPress={onLogout}
                  style={{
                    backgroundColor: C.badSoft || 'rgba(248,81,73,0.1)',
                    borderRadius: 6,
                    paddingHorizontal: 10,
                    paddingVertical: 5,
                    borderWidth: 1,
                    borderColor: C.badSoftBorder || 'rgba(248,81,73,0.2)',
                  }}
                >
                  <Text
                    style={{
                      color: C.bad,
                      fontSize: 10,
                      fontWeight: '800',
                      letterSpacing: 1,
                    }}
                  >
                    LOGOUT
                  </Text>
                </TouchableOpacity>
              </View>
            ),
            tabBarActiveTintColor: C.accent,
            tabBarInactiveTintColor: C.muted,
            tabBarStyle: {
              backgroundColor: C.card,
              borderTopWidth: 1,
              borderTopColor: C.border,
              height: 64,
              paddingBottom: 8,
              paddingTop: 6,
            },
            tabBarLabelStyle: {
              fontSize: 10,
              fontWeight: '700',
              letterSpacing: 0.8,
              textTransform: 'uppercase',
            },
            sceneStyle: {
              backgroundColor: C.bg,
            },
          }}
        >
          <Tab.Screen
            name="LiveMonitor"
            component={LiveMonitorScreen}
            options={{
              title: 'Monitor',
              headerTitle: `◈  HIDESPEC — ${user.role.toUpperCase()}`,
              tabBarIcon: ({ color }) => (
                <View style={{ alignItems: 'center' }}>
                  <Text style={{ fontSize: 20, color }}>◉</Text>
                </View>
              ),
            }}
          />

          <Tab.Screen
            name="Analytics"
            component={AnalyticsScreen}
            options={{
              title: 'Analytics',
              headerTitle: '◈  HIDESPEC — ANALYTICS',
              tabBarIcon: ({ color }) => (
                <View style={{ alignItems: 'center' }}>
                  <Text style={{ fontSize: 20, color }}>▦</Text>
                </View>
              ),
            }}
          />

          <Tab.Screen
            name="About"
            component={AboutScreen}
            options={{
              title: 'About',
              headerTitle: '◈  HIDESPEC — ABOUT',
              tabBarIcon: ({ color }) => (
                <View style={{ alignItems: 'center' }}>
                  <Text style={{ fontSize: 20, color }}>◈</Text>
                </View>
              ),
            }}
          />
        </Tab.Navigator>
      </NavigationContainer>
    </Animated.View>
  );
}

function AppContent() {
  const { theme: C, themeMode } = useAppTheme();
  const [user, setUser] = useState(null);

  const handleLogin = (userData) => {
    setUser(userData);
  };

  const handleLogout = () => {
    setUser(null);
  };

  if (!user) {
    return (
      <>
        <StatusBar
          barStyle={themeMode === 'dark' ? 'light-content' : 'dark-content'}
          backgroundColor={C.bg}
        />
        <LoginScreen onLogin={handleLogin} />
      </>
    );
  }

  return <MainApp user={user} onLogout={handleLogout} />;
}

export default function App() {
  return (
    <AppThemeProvider>
      <AppContent />
    </AppThemeProvider>
  );
}
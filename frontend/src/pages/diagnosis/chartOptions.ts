// P2-08: extracted ECharts option builders for the Diagnosis page. Pure functions.
// P2-03: callers should wrap these in useMemo keyed on their data dependencies so
// the option object is not rebuilt every render.

import type { DiagnosisResult, PredictionPoint } from './types'

export function buildRadarOption(dimensions: DiagnosisResult['dimensions'], dark = false) {
  const textColor = dark ? '#e0e0e0' : '#333'
  const axisColor = dark ? '#444' : '#e8e8e8'
  const splitColor = dark ? '#333' : '#f0f0f0'
  return {
    tooltip: { trigger: 'item' as const },
    legend: {
      data: ['当前诊断'],
      bottom: 0,
      textStyle: { color: textColor, fontSize: 12 },
    },
    radar: {
      center: ['50%', '48%'],
      radius: '65%',
      indicator: [
        { name: '技术面', max: 100 },
        { name: '资金面', max: 100 },
        { name: '基本面', max: 100 },
        { name: 'AI预测', max: 100 },
        { name: '情绪面', max: 100 },
      ],
      axisName: { color: textColor, fontSize: 11 },
      splitArea: {
        areaStyle: { color: [splitColor, 'transparent'] },
      },
      axisLine: { lineStyle: { color: axisColor } },
      splitLine: { lineStyle: { color: axisColor } },
    },
    series: [{
      type: 'radar',
      name: '诊断',
      data: [{
        value: [
          dimensions.technical,
          dimensions.capital,
          dimensions.fundamental,
          dimensions.ai_prediction,
          dimensions.sentiment,
        ],
        name: '当前诊断',
      }],
      symbol: 'circle',
      symbolSize: 5,
      lineStyle: { color: '#1677ff', width: 2 },
      areaStyle: { color: 'rgba(22,119,255,0.15)' },
      itemStyle: { color: '#1677ff' },
    }],
  }
}

export function buildCompareRadarOption(
  stocks: { name: string; dims: DiagnosisResult['dimensions'] }[],
  dark = false,
) {
  const textColor = dark ? '#e0e0e0' : '#333'
  const axisColor = dark ? '#444' : '#e8e8e8'
  const splitColor = dark ? '#333' : '#f0f0f0'
  const colors = ['#1677ff', '#52c41a', '#faad14', '#ff4d4f', '#722ed1']
  return {
    tooltip: { trigger: 'item' as const },
    legend: {
      data: stocks.map(s => s.name),
      bottom: 0,
      textStyle: { color: textColor, fontSize: 11 },
    },
    radar: {
      center: ['50%', '45%'],
      radius: '60%',
      indicator: [
        { name: '技术面', max: 100 },
        { name: '资金面', max: 100 },
        { name: '基本面', max: 100 },
        { name: 'AI预测', max: 100 },
        { name: '情绪面', max: 100 },
      ],
      axisName: { color: textColor, fontSize: 11 },
      splitArea: {
        areaStyle: { color: [splitColor, 'transparent'] },
      },
      axisLine: { lineStyle: { color: axisColor } },
      splitLine: { lineStyle: { color: axisColor } },
    },
    series: stocks.map((s, i) => ({
      type: 'radar',
      name: s.name,
      data: [{
        value: [
          s.dims.technical,
          s.dims.capital,
          s.dims.fundamental,
          s.dims.ai_prediction,
          s.dims.sentiment,
        ],
        name: s.name,
      }],
      symbol: 'circle',
      symbolSize: 4,
      lineStyle: { color: colors[i % colors.length], width: 2 },
      areaStyle: { color: 'transparent' },
      itemStyle: { color: colors[i % colors.length] },
    })),
  }
}

export function buildKlinePredictionOption(
  historical: PredictionPoint[],
  predictions: PredictionPoint[],
  dark = false,
) {
  const textColor = dark ? '#e0e0e0' : '#333'
  const borderColor = dark ? '#333' : '#e5e5e5'

  const allDates = [
    ...historical.map(p => p.date),
    ...predictions.map(p => p.date),
  ]

  // Build candlestick data: [open, close, low, high]
  const histCandle = historical.map(p => [p.open, p.close, p.low, p.high])

  return {
    tooltip: {
      trigger: 'axis' as const,
      axisPointer: { type: 'cross' as const },
    },
    legend: {
      data: ['历史K线', 'AI预测'],
      bottom: 0,
      textStyle: { color: textColor, fontSize: 12 },
    },
    grid: {
      left: '3%', right: '4%', top: '10%', bottom: '14%',
      containLabel: true,
    },
    xAxis: {
      type: 'category' as const,
      data: allDates,
      axisLine: { lineStyle: { color: borderColor } },
      axisLabel: {
        color: textColor,
        fontSize: 10,
        rotate: 30,
        interval: Math.max(Math.floor(allDates.length / 8), 0),
      },
    },
    yAxis: {
      type: 'value' as const,
      scale: true,
      axisLine: { lineStyle: { color: borderColor } },
      splitLine: { lineStyle: { color: borderColor, type: 'dashed' as const } },
      axisLabel: { color: textColor, fontSize: 10 },
    },
    series: [
      {
        name: '历史K线',
        type: 'candlestick',
        data: histCandle,
        itemStyle: {
          color: '#ef232a',
          color0: '#14b143',
          borderColor: '#ef232a',
          borderColor0: '#14b143',
        },
      },
      {
        name: 'AI预测',
        type: 'line',
        data: [
          ...historical.map(() => null),
          ...predictions.map(p => [p.open, p.close, p.low, p.high]),
        ],
      },
    ],
  }
}

// Build a more practical version: line chart overlay
export function buildPredictionOverlayChart(
  historical: PredictionPoint[],
  predictions: PredictionPoint[],
  dark = false,
) {
  const textColor = dark ? '#e0e0e0' : '#333'
  const borderColor = dark ? '#333' : '#e5e5e5'

  const histDates = historical.map(p => p.date)
  const histClose = historical.map(p => p.close)
  const predDates = predictions.map(p => p.date)

  const allDates = [...histDates, ...predDates]
  const lastHistIdx = histDates.length - 1

  const predCloseFull = [
    ...new Array(histDates.length).fill(null),
    ...predictions.map(p => p.close),
  ] as (number | null)[]

  if (histClose.length > 0 && predictions.length > 0) {
    predCloseFull[lastHistIdx] = histClose[lastHistIdx]
  }

  const predHighFull = [
    ...new Array(histDates.length).fill(null),
    ...predictions.map(p => p.high),
  ] as (number | null)[]
  const predLowFull = [
    ...new Array(histDates.length).fill(null),
    ...predictions.map(p => p.low),
  ] as (number | null)[]
  if (histClose.length > 0 && predictions.length > 0) {
    predHighFull[lastHistIdx] = histClose[lastHistIdx]
    predLowFull[lastHistIdx] = histClose[lastHistIdx]
  }

  return {
    tooltip: {
      trigger: 'axis' as const,
      formatter: (params: unknown) => {
        if (!Array.isArray(params) || params.length === 0) return ''
        const ps = params as Array<{ axisValue?: string; value?: number | null; marker?: string; seriesName?: string }>
        const date = ps[0].axisValue
        let html = `<div style="font-weight:bold;margin-bottom:4px">${date}</div>`
        ps.forEach(p => {
          if (p.value != null) {
            html += `<div>${p.marker} ${p.seriesName}: ${Number(p.value).toFixed(2)}</div>`
          }
        })
        return html
      },
    },
    legend: {
      data: ['历史收盘', 'AI预测', '预测上限', '预测下限'],
      bottom: 0,
      textStyle: { color: textColor, fontSize: 11 },
    },
    grid: { left: '3%', right: '4%', top: '10%', bottom: '14%', containLabel: true },
    xAxis: {
      type: 'category' as const,
      data: allDates,
      axisLine: { lineStyle: { color: borderColor } },
      axisLabel: {
        color: textColor, fontSize: 10,
        interval: Math.max(Math.floor(allDates.length / 10), 0),
      },
    },
    yAxis: {
      type: 'value' as const,
      scale: true,
      axisLine: { lineStyle: { color: borderColor } },
      splitLine: { lineStyle: { color: borderColor, type: 'dashed' as const } },
      axisLabel: { color: textColor, fontSize: 10 },
    },
    series: [
      {
        name: '历史收盘',
        type: 'line',
        data: histClose,
        smooth: false,
        lineStyle: { color: '#1677ff', width: 2 },
        itemStyle: { color: '#1677ff' },
        symbol: 'none',
      },
      {
        name: 'AI预测',
        type: 'line',
        data: predCloseFull,
        smooth: true,
        lineStyle: { color: '#fa8c16', width: 2, type: 'dashed' as const },
        itemStyle: { color: '#fa8c16' },
        symbol: 'circle',
        symbolSize: 4,
        connectNulls: true,
      },
      {
        name: '预测上限',
        type: 'line',
        data: predHighFull,
        smooth: true,
        lineStyle: { color: '#ffd591', width: 1, type: 'dotted' as const },
        itemStyle: { color: '#ffd591' },
        symbol: 'none',
        connectNulls: true,
      },
      {
        name: '预测下限',
        type: 'line',
        data: predLowFull,
        smooth: true,
        lineStyle: { color: '#ffd591', width: 1, type: 'dotted' as const },
        itemStyle: { color: '#ffd591' },
        symbol: 'none',
        connectNulls: true,
        areaStyle: {
          color: {
            type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(250,140,22,0.08)' },
              { offset: 1, color: 'rgba(250,140,22,0.02)' },
            ],
          },
        },
      },
    ],
  }
}

<template>
  <div id="markdown" v-cloak>
    <!-- <details>
      <summary>Epcot Center</summary>
      <p>Epcot is a theme park at Walt Disney World Resort featuring exciting attractions, international pavilions,
        award-winning fireworks and seasonal special events.</p>
    </details> -->
    <div class="text" v-html="compiledMarkdown"></div>
    <ArtifactRenderer
      v-for="(artifact, index) in artifacts"
      :key="index"
      :artifact="artifact"
    />
    <!-- <div ref="chartDom" style="width: 100%; height: 200px;"></div> -->
  </div>
</template>

<script>

import { watch } from "less";
import markdownIt from "markdown-it";
import markdownItTable from 'markdown-it-multimd-table';
import ArtifactRenderer from './ArtifactRenderer.vue';


export default {
  components: { ArtifactRenderer },
  props: ['content'],
  data() {
    return {
      strData: '',
      chartOptions: {} // 存储图表配置
    }
  },
  computed: {
    compiledMarkdown() {
      const parsed = this.parseArtifacts(this.content);
      const md = new markdownIt({
        html: true,         // 启用 HTML 标签
        linkify: true,      // 自动转换 URL 为链接
        typographer: true,  // 启用印刷字符替换
        breaks: true,       // 转换段落里的 '\n' 到 <br>
        // 高性能高亮函数
        // highlight: function (str, lang) {
        //   if (lang && highlightjs.getLanguage(lang)) {
        //     try {
        //       return highlightjs.highlight(lang, str).value;
        //     } catch (__) { }
        //   }
        //   return '';
        // }
      });
      md.use(markdownItTable);

      // document.querySelectorAll('details').forEach(details => {
      //   details.removeAttribute('open');
      // });



      //  let str = '```echarts\n{\n  \"title\": {\n    \"text\": \"广汽埃安4月库存及库存度\",\n    \"
      // \": \"center\"\n  },\n  \"xAxis\": {\n    \"type\": \"category\",\n    \"data\": [\"广汽埃安\"]\n  },\n  \"yAxis\": [\n    {\n      \"type\": \"value\",\n      \"name\": \"库存\"\n    },\n    {\n      \"type\": \"value\",\n      \"name\": \"库存度\",\n      \"position\": \"right\"\n    }\n  ],\n  \"series\": [\n    {\n      \"name\": \"库存\",\n      \"type\": \"bar\",\n      \"data\": [69670]\n    },\n    {\n      \"name\": \"库存度\",\n      \"type\": \"line\",\n      \"yAxisIndex\": 1,\n      \"data\": [2.8]\n    }\n  ],\n  \"legend\": {\n    \"data\": [\"库存\", \"库存度\"],\n    \"top\": \"bottom\"\n  }\n}\n```'
      const self = this;

      md.renderer.rules.fence = (tokens, idx) => {
        const token = tokens[idx];
        if (token.info.trim() === 'echarts') {
          // 返回图表容器
          this.$nextTick(() => {
            this.renderAllCharts();
          });
          try {
            const optionStr = token.content.replace(/\s+/g, ' ').replace(/(\d+)\s*([+\-*/])\s*(\d+)/g, (_, a, op, b) => {
              const numA = Number(a);
              const numB = Number(b);
              switch (op) {
                case '+': return numA + numB;
                case '-': return numA - numB;
                case '*': return numA * numB;
                case '/': return _;
                default: return _; // 未知运算符则原样返回（理论上不会执行）
              }
            }).trim();
            const chartId = 'chart-' + Math.random().toString(36).substr(2, 9);
            // 存储图表配置
            console.log(JSON.parse(optionStr), "11111111111111")
            let arrData = []
            let op = JSON.parse(optionStr)
            op.series.forEach(item => {
              item.data.forEach((list) => {
                arrData.push(list)
              })
            });
            const max = Math.max(...arrData); //数组最大值
            let maxwi = max.toString().length + '4' + 'px'

            op.grid = { //设置左边刻度距离
              left: maxwi,
            }

            op.legend = {
              type: 'scroll', // 启用滚动模式
              orient: 'horizontal', // 水平方向排列
        
              top: 'bottom'
            }
            op.tooltip = {
              // appendToBody: true, // 关键配置：将提示框挂载到 body
              trigger: 'axis', // item或 'axis'
              confine: true, // 关键配置：将提示框限制在图表区域内
            }
            if (op.series.length && op.series[0].type == 'pie') {  //饼图的样式处理
              // op.series[0].center = ['50%', '50%'];
              op.tooltip.trigger = 'item'
            }

            self.chartOptions[chartId] = op;

            return `<div id="${chartId}" class="echarts-container"  style=" height: 300px;"></div>`;
          } catch (err) {
            console.error('解析ECharts配置出错:', err);
            return `<pre><code>${token.content}</code></pre>`;
          }


        }
        // 其他代码块默认渲染
        return `<pre><code>${token.content}</code></pre>`;
      };




      return md.render(parsed.markdown);


    },
    artifacts() {
      return this.parseArtifacts(this.content).artifacts;
    }
  },
  watch: {

  },
  mounted() {
    // this.initChart();
    this.$nextTick(() => {
      this.renderAllCharts();
    });
  },
  methods: {
    parseArtifacts(content) {
      const source = content == null ? '' : String(content);
      const artifacts = [];
      let markdown = source;
      const artifactFence = /```artifact\s*([\s\S]*?)```/g;
      const jsonFence = /```json\s*([\s\S]*?)```/g;
      markdown = this.collectArtifacts(markdown, artifactFence, artifacts);
      markdown = this.collectArtifacts(markdown, jsonFence, artifacts);
      return { markdown, artifacts };
    },
    collectArtifacts(source, regex, artifacts) {
      return source.replace(regex, (full, body) => {
        try {
          const data = JSON.parse(body.trim());
          if (data && (data.artifact_type || data.type) && data.payload) {
            artifacts.push(data);
            return '';
          }
        } catch (e) {
          return full;
        }
        return full;
      });
    },
    childMethod(val) {
      console.log('update')
    },
    nihao() {
      console.log('nihao')
    },
    initChart() {
      // 初始化图表实例
      const chartDom = this.$refs.chartDom;
      // const myChart = echarts.init(chartDom);
      const myChart = window.echarts.init(chartDom);

      // 配置图表选项
      const option = {
        title: {
          text: 'ECharts 入门示例'
        },
        tooltip: {},
        xAxis: {
          data: ['衬衫', '羊毛衫', '雪纺衫', '裤子', '高跟鞋', '袜子']
        },
        yAxis: {},
        series: [{
          name: '销量',
          type: 'bar',
          data: [5, 20, 36, 10, 10, 20]
        }]
      };

      // 使用配置项渲染图表
      myChart.setOption(option);
    },
    renderAllCharts() {
      Object.keys(this.chartOptions).forEach(chartId => {
        const chartDom = document.getElementById(chartId);
        if (chartDom) {
          const chart = echarts.init(chartDom);
          chart.setOption(this.chartOptions[chartId]);
          // 可选：监听窗口变化自动调整图表大小
          window.addEventListener('resize', () => {
            chart.resize();
          });
          // 在组件销毁时，也销毁图表实例
          this.$once('hook:beforeDestroy', () => {
            chart.dispose();
          });
        }
      });
    }
  }
}
</script>
<style lang="less">
#markdown {
  width: 100%;

  .text {
    will-change: transform;
    contain: content;
  }

  [v-cloak] {
    display: none;
  }

  table {
    // width: 100%;
    border-collapse: collapse;

    margin: 5px;
    // border: 1px solid rgb(234, 236, 240);

  }

  th,
  td {
    border: 1px solid rgb(234, 236, 240);
    padding: 8px;
    text-align: center !important;
    background-color: #f8fafa;
    font-size: 13px;

  }

  th {

    background-color: #e1e7fd;
    text-align: center !important;
    white-space: nowrap;
    // color: #f8fafa;
  }

  tr {
    text-align: center !important;
    white-space: nowrap;
  }

  thead {
    border-radius: 8px;
  }

  p {
    color: #101828;
    font-size: 13px;


  }



  details {
    p {
      color: #827c7c;
      font-size: 13px;
    }
  }

  // font-size: 0.35rem;

  pre {
    font-size: 0.3rem;

    code {
      width: 100%;
      word-wrap: break-word;
      /* 允许长单词换行 */
      word-break: break-all;
      /* 强制任意字符处换行 */
      white-space: normal;
      /* 默认换行行为 */
    }
  }

  /* 强制表格宽度不超过容器 */
  table {
    width: 100%;
    max-width: 100%;
    table-layout: fixed;
    word-wrap: break-word;
  }

  /* 可选：添加滚动条 */
  table {
    display: block;
    overflow-x: auto;
  }

  h1 {
    font-size: 15px;
    color: #292525;
  }

  strong {
    color: #292525;
  }

  h2 {
    font-size: 15px;
    color: #292525;
  }

  h3 {
    font-size: 13px;
    color: #292525;

  }

  h4 {
    font-size: 13px;
    color: #292525;

  }

  .shujuText {
    font-size: 12px;
    color: #999;
    font-weight: 400;
  }

  ol {
    li {
      margin: 10px 0px;

      color: #292525;
      font-size: 13px;

      strong {
        font-size: 13px;
      }

      list-style-type: decimal;
      list-style-position: inside;



      /* 标记与内容对齐 */
      /* 默认值，实心圆点 */
      // font-size: 15px;
      // font-weight: 600;
    }

    li p:first-child {
      display: inline;
      margin-left: 0;
    }

    li::marker {
      font-size: 13px;
      font-weight: bolder;
    }
  }

  ul {
    li {
      margin: 10px 0px;
      color: #292525;
      font-size: 13px;
      list-style-type: disc;
      list-style-position: inside;

      text-indent: -1em;
      /* 文本向左移动1em */
      padding-left: 2em;
      /* 整体缩进2em */
      /* 标记与内容对齐 */
    }

    li p:first-child {
      display: inline;
      margin-left: 0;
    }
  }

  text {
    font-size: 13px;
  }

  .itemStr {


    border-radius: 5px;
    display: block;
    background: #f0f2f4;
    padding: 5px 0px 5px 10px;
    font-size: 11px;
    color: #101828;

    p {
      font-size: 11px;
      margin: 5px 5px 5px 0px;
    }
  }


}
</style>
